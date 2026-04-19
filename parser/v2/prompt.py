"""
Prompt-Template und Builder für Parser v2.0.
v2 nutzt den Ollama format-Parameter (Grammar-Enforcement) —
der Prompt muss daher kein JSON-Struktur-Hinweis enthalten.
"""

EXTRACTION_PROMPT = """Du bist ein Datenextraktions-Assistent für Konzertticket-Anzeigen von willhaben.at.

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
KRITISCHE REGELN — IMMER BEACHTEN
════════════════════════════════════════

REGEL K1 — EVENT-NAME NICHT verwechseln:
  Der event_name ist NUR der Künstlername oder Tourname.
  NICHT: Veranstaltungsort (z.B. "Gasometer", "Stadthalle", "Arena Wien")
  NICHT: Label oder Promotion-Firma (z.B. "pgLang", "Live Nation", "OVO Sound")
  NICHT: Sponsor (z.B. "Red Bull Music", "Erste Bank")
  Beispiel: "pgLang / OVO Sound präsentiert Kendrick Lamar" → event_name = "Kendrick Lamar"
  Beispiel: "Gasometer Wien: Skinshape" → event_name = "Skinshape", venue = "Gasometer Wien"

REGEL K2 — TRIBUTE-SHOWS erkennen:
  Wenn "Tribute", "tribute to", "tribute show", "die Beste von X", "Hommage an" → es ist KEIN echter Auftritt.
  → event_name MUSS "Tribute" im Namen enthalten (z.B. "Adele Tribute Show")
  → confidence = "mittel" (Originalpreis unbekannt, Tribute-Preise stark variieren)
  → kategorie aus Venue ableiten wenn möglich, sonst "Unbekannt"
  → confidence_grund: "Tribute-Show, kein Originalpreis bekannt"

REGEL K3 — KATEGORIE aus VENUE ableiten (nur wenn Kategorie nicht explizit genannt):
  Opernhaus / Konzerthaus / Musikverein → "Sitzplatz"
  Kleiner Club/Bar (< ~1000 Personen, z.B. WUK, Flex, B72, Chelsea) → "Stehplatz"
  Stadion / großes Festival-Gelände → "Stehplatz" (wenn nicht anders angegeben)
  Kein Venue oder Venue unbekannt → "Unbekannt"

════════════════════════════════════════
FEW-SHOT BEISPIELE
════════════════════════════════════════

--- BEISPIEL 1 — Taylor Swift: Privatverkauf, Stehplatz, OVP explizit ---
Titel: Taylor Swift Eras Tour Wien 2026 – 2x Stehplatz Golden Circle
Preis: € 700
Beschreibung: Verkaufe 2 Golden Circle Stehplatz-Tickets für Taylor Swift am 12.07.2026 im Ernst-Happel-Stadion Wien. Originalpreis war je 149,90€. Muss leider absagen. Beide zusammen 700€.

Erwartetes Ergebnis:
events: [{event_name: "Taylor Swift Eras Tour", event_datum: "2026-07-12", venue: "Ernst-Happel-Stadion", stadt: "Wien", kategorie: "Stehplatz", anzahl_karten: 2, angebotspreis_gesamt: 700.0, preis_ist_pro_karte: false, originalpreis_pro_karte: 149.9, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL 2 — Adele Tribute: REGEL K2 anwenden ---
Titel: Adele Tribute Show Wien – 1x VIP Ticket
Preis: € 85
Beschreibung: 1 VIP Ticket für "The Adele Tribute Show" am 03.05.2026, Wiener Stadthalle. Tribute Band, kein echter Auftritt. OVP 65€.

Erwartetes Ergebnis:
events: [{event_name: "Adele Tribute Show", event_datum: "2026-05-03", venue: "Wiener Stadthalle", stadt: "Wien", kategorie: "VIP", anzahl_karten: 1, angebotspreis_gesamt: 85.0, preis_ist_pro_karte: true, originalpreis_pro_karte: 65.0, confidence: "mittel", confidence_grund: "Tribute-Show, kein Originalpreis bekannt"}]

--- BEISPIEL 3 — Kendrick Lamar: REGEL K1 — Label nicht als Event-Name ---
Titel: pgLang / OVO Sound präsentiert Kendrick Lamar – Wien 2026
Preis: € 280
Beschreibung: 1 Ticket für Kendrick Lamar "Grand National Tour" am 15.06.2026. Gasometer Wien. Stehplatz. Preis pro Karte 280€. OVP laut Ticket 89,90€.

Erwartetes Ergebnis:
events: [{event_name: "Kendrick Lamar", event_datum: "2026-06-15", venue: "Gasometer Wien", stadt: "Wien", kategorie: "Stehplatz", anzahl_karten: 1, angebotspreis_gesamt: 280.0, preis_ist_pro_karte: true, originalpreis_pro_karte: 89.9, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL 4 — Zuckerwatte Festival: Festival-Name ≠ Venue ---
Titel: Zuckerwatte Festival 2026 – 2x Tagesticket Samstag
Preis: € 130
Beschreibung: Verkaufe 2 Samstag-Tagestickets für das Zuckerwatte Festival 2026, Stadtpark Wien, 04.07.2026. Damals 55€ pro Stück. Beide zusammen 130€.

Erwartetes Ergebnis:
events: [{event_name: "Zuckerwatte Festival 2026", event_datum: "2026-07-04", venue: "Stadtpark Wien", stadt: "Wien", kategorie: "Stehplatz", anzahl_karten: 2, angebotspreis_gesamt: 130.0, preis_ist_pro_karte: false, originalpreis_pro_karte: 55.0, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL 5 — Skinshape: REGEL K1 Venue + REGEL K3 Kategorie ---
Titel: Skinshape Wien – Gasometer – 1x Ticket
Preis: € 45
Beschreibung: 1 Ticket für Skinshape Live am 22.09.2026 im Gasometer Wien. Kein Sitzplatz, stehend. Originalpreis 29€.

Erwartetes Ergebnis:
events: [{event_name: "Skinshape", event_datum: "2026-09-22", venue: "Gasometer Wien", stadt: "Wien", kategorie: "Stehplatz", anzahl_karten: 1, angebotspreis_gesamt: 45.0, preis_ist_pro_karte: true, originalpreis_pro_karte: 29.0, confidence: "hoch", confidence_grund: null}]

--- BEISPIEL 6 — Böhse Onkelz: Datums-Auffälligkeit (date appears to be past year) ---
Titel: Böhse Onkelz – Hockenheimring 2025 – 2 Tickets
Preis: € 200
Beschreibung: 2 Stehplatz Tickets für Böhse Onkelz am 21.06.2025 Hockenheimring. Originalpreis je 79€. Verkaufe beide für 200€.

Erwartetes Ergebnis (Datum exakt wie im Text, auch wenn vergangenheit — date_shift_heuristik korrigiert ggf. separat):
events: [{event_name: "Böhse Onkelz", event_datum: "2025-06-21", venue: "Hockenheimring", stadt: null, kategorie: "Stehplatz", anzahl_karten: 2, angebotspreis_gesamt: 200.0, preis_ist_pro_karte: false, originalpreis_pro_karte: 79.0, confidence: "mittel", confidence_grund: "Eventdatum liegt in der Vergangenheit, möglicher Jahresfehler"}]

--- BEISPIEL 7 — Kategorie-Index: Händler mit numerischer Liste → 2 Objekte ---
Titel: Ed Sheeran Wien 2026 – Sitzplatz & VIP verfügbar
Preis: € 250
Beschreibung: Ed Sheeran "Mathematics Tour" Wien 20.08.2026, Ernst-Happel-Stadion.
1) Sitzplatz Tribüne – Preis pro Karte EUR 250,- (OVP 139€)
2) VIP Hospitality Package – Preis pro Karte EUR 450,- (OVP 299€)

Erwartetes Ergebnis (2 Objekte!):
events: [
  {event_name: "Ed Sheeran", event_datum: "2026-08-20", venue: "Ernst-Happel-Stadion", stadt: "Wien", kategorie: "Sitzplatz", anzahl_karten: null, angebotspreis_gesamt: null, preis_ist_pro_karte: true, originalpreis_pro_karte: 139.0, confidence: "hoch", confidence_grund: null},
  {event_name: "Ed Sheeran", event_datum: "2026-08-20", venue: "Ernst-Happel-Stadion", stadt: "Wien", kategorie: "VIP", anzahl_karten: null, angebotspreis_gesamt: null, preis_ist_pro_karte: true, originalpreis_pro_karte: 299.0, confidence: "hoch", confidence_grund: null}
]

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

# Backwards compatibility alias
PROMPT_TEMPLATE = EXTRACTION_PROMPT


def build_prompt(context: str) -> str:
    """Baut den vollständigen Prompt mit dem Anzeigen-Kontext."""
    return EXTRACTION_PROMPT.replace("{context}", context)
