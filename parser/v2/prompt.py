"""
Prompt-Template und Builder für Parser v2.0.
v2 nutzt den Ollama format-Parameter (Grammar-Enforcement) —
der Prompt muss daher kein JSON-Struktur-Hinweis enthalten.
"""

PROMPT_TEMPLATE = """Du bist ein Datenextraktions-Assistent für Konzertticket-Anzeigen von willhaben.at.

Extrahiere die Ticket-Informationen aus der Anzeige unten.
Antworte AUSSCHLIESSLICH mit den Feldern des vorgegebenen Schemas. Kein Fließtext.

Der Anzeigentext enthält willhaben-Navigation (z.B. "Zum Inhalt", "Nachrichten", "Rechtlicher Hinweis"). Ignoriere diesen Rausch vollständig. Konzentriere dich auf Titel, Preis und Beschreibung.

════════════════════════════════════════
SCHRITT 1 — ORIGINALPREIS SUCHEN
════════════════════════════════════════

Durchsuche TITEL und BESCHREIBUNG nach Originalpreis-Mustern:

  Direkte Bezeichnungen:
    Originalpreis / OVP / NP / Neupreis / UVP / Aufgedruckter Preis

  Umgangssprachlich:
    "damals um X€ gekauft" / "damals um X€ pro Stück gekauft"
    "habe X€ bezahlt" / "gekauft um X€" / "Ticketpreis war X€"

  Im Titel in Klammern:
    "(Originalpreis X€)" / "(NP X€)" / "(OVP: X€)"

→ Trage den Originalpreis IMMER als Preis PRO KARTE ein (nie als Gesamtbetrag).
→ Kein Originalpreis erkennbar → null

════════════════════════════════════════
SCHRITT 2 — PREIS EINORDNEN
════════════════════════════════════════

angebotspreis_gesamt = Gesamtbetrag für ALLE angebotenen Karten zusammen.
  Wenn nur Preis pro Karte bekannt und Anzahl bekannt: Preis × Anzahl = Gesamt.
  Wenn Anzahl unbekannt (Händler mit offener Stückzahl): null.

preis_ist_pro_karte = ob der im Text genannte Preis pro Einzelkarte gilt.
  true  → "Preis pro Karte", "je Ticket", "pro Stück"
  false → "beide zusammen", "für X Karten zusammen"
  null  → unklar

════════════════════════════════════════
SCHRITT 3 — ANZAHL OBJEKTE IM events-ARRAY
════════════════════════════════════════

WICHTIGSTE REGEL: Händler mit mehreren Ticket-Kategorien desselben Events
→ EIN OBJEKT PRO KATEGORIE im events-Array. Nicht zusammenfassen!

Beispiel: "1) Front-of-Stage EUR 129 / 2) Stehplatz EUR 99" → 2 Objekte!

Normalfall (Privatperson, eine Kategorie): 1 Objekt.
Mehrere VERSCHIEDENE Events in einer Anzeige: 1 Objekt, event_name="MEHRERE", confidence=niedrig.

════════════════════════════════════════
FEW-SHOT BEISPIELE
════════════════════════════════════════

--- BEISPIEL A: Privatverkauf, OVP "damals um X€ pro Stück" ---
Titel: Dante YN - Tranquille Tour 2026 - Wien - 2x Tickets
Preis: € 40
Beschreibung: Krankheitsbedingt verkaufe ich 2 Tickets für Dante YN am 14.4. in Wien (FLUCC).
Habe die Tickets damals um 30€ pro Stück gekauft und würde beide zusammen für 40€ weitergeben.

Erwartetes Ergebnis:
events: [{event_name: "Dante YN - Tranquille Tour 2026", event_datum: "2026-04-14", venue: "FLUCC", stadt: "Wien", kategorie: "Unbekannt", anzahl_karten: 2, angebotspreis_gesamt: 40.0, preis_ist_pro_karte: false, originalpreis_pro_karte: 30.0, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL B: Händler, 1 Kategorie, OVP explizit ---
Titel: BERQ / Stehplatz / 18.11.26 Graz
Preis: € 85
Beschreibung: BERQ Live in Graz 18.11.26 Helmuth List Halle
4 x Stehplatz – Preis pro Karte 85€ – auch einzeln abzugeben
Originalpreis Stehplätze 58,90 € inkl.Gebühren

Erwartetes Ergebnis:
events: [{event_name: "BERQ", event_datum: "2026-11-18", venue: "Helmuth List Halle", stadt: "Graz", kategorie: "Stehplatz", anzahl_karten: 4, angebotspreis_gesamt: 340.0, preis_ist_pro_karte: true, originalpreis_pro_karte: 58.9, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL C: Händler, 2 Kategorien → ZWINGEND 2 Objekte ---
Titel: Pizzera & Jaus 30.05.2026 Salzburg! Front of Stage & Stehplatz Tickets!
Preis: € 99
Beschreibung: Pizzera und Jaus, Salzburg, 30.05.2026, Residenzplatz Salzburg.
1) Stehplatz Front-of-Stage* Preis pro Karte EUR 129,-
2) Stehplatz** Preis pro Karte EUR 99,-
Aufgedruckter Originalpreis Front-of-Stage* EUR 97,49
Aufgedruckter Originalpreis Stehplatz** EUR 77,49

Erwartetes Ergebnis (2 Objekte!):
events: [
  {event_name: "Pizzera & Jaus", event_datum: "2026-05-30", venue: "Residenzplatz Salzburg", stadt: "Salzburg", kategorie: "Front-of-Stage", anzahl_karten: null, angebotspreis_gesamt: null, preis_ist_pro_karte: true, originalpreis_pro_karte: 97.49, confidence: "hoch", confidence_grund: null},
  {event_name: "Pizzera & Jaus", event_datum: "2026-05-30", venue: "Residenzplatz Salzburg", stadt: "Salzburg", kategorie: "Stehplatz", anzahl_karten: null, angebotspreis_gesamt: null, preis_ist_pro_karte: true, originalpreis_pro_karte: 77.49, confidence: "hoch", confidence_grund: null}
]

--- BEISPIEL D: OVP im Titel in Klammern ---
Titel: Olivia Dean - Köln, 11.5., Lounge, (Originalpreis 300€), Plätze in 1. Reihe inkl Buffet
Preis: € 290

Erwartetes Ergebnis:
events: [{event_name: "Olivia Dean", event_datum: "2026-05-11", venue: null, stadt: "Köln", kategorie: "VIP", anzahl_karten: null, angebotspreis_gesamt: 290.0, preis_ist_pro_karte: null, originalpreis_pro_karte: 300.0, confidence: "mittel", confidence_grund: "Anzahl Karten unklar; OVP aus Titel entnommen"}]

--- BEISPIEL E: Privatverkauf, Datum fehlt ---
Titel: 2 Konzerttickets Stefanie Heinzmann
Preis: € 70
Beschreibung: Verkaufe 2 Tickets für Stefanie Heinzmann. Preis 35€ pro Stück.

Erwartetes Ergebnis:
events: [{event_name: "Stefanie Heinzmann", event_datum: null, venue: null, stadt: null, kategorie: "Unbekannt", anzahl_karten: 2, angebotspreis_gesamt: 70.0, preis_ist_pro_karte: false, originalpreis_pro_karte: 35.0, confidence: "mittel", confidence_grund: "Eventdatum fehlt"}]

════════════════════════════════════════
CONFIDENCE-REGELN
════════════════════════════════════════

hoch:    event_name, event_datum, angebotspreis_gesamt und anzahl_karten alle eindeutig
         ODER Händler mit klarem Preis-pro-Karte (dann darf anzahl_karten null sein)
mittel:  1-2 Felder fehlen/unsicher, Kernaussage klar
niedrig: Event unklar, Preis nicht zuordenbar, kein Konzertticket

Setze NIEMALS einen Wert wenn du ihn nur erraten würdest — lieber null.

════════════════════════════════════════
AKTUELLE ANZEIGE
════════════════════════════════════════

{context}"""


def build_prompt(context: str) -> str:
    """Baut den vollständigen Prompt mit dem Anzeigen-Kontext."""
    return PROMPT_TEMPLATE.replace("{context}", context)
