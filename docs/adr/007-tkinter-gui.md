# ADR-007: Tkinter GUI statt Web-Frontend

**Status:** Accepted
**Datum:** 2026-04-17

**Kontext:** Einzel-User macOS-Desktop-App. Kein Server gewünscht. Einfache Installation ohne zusätzliche npm/node-Dependencies.

**Entscheidung:** Tkinter (Python Standard-Library). Tabbed-Interface mit 4 Tabs: Engine, Zeitplan, Status, Dashboard.

**Begründung:** Tkinter ist Teil der Python Standard-Library — kein zusätzliches `pip install`. Ausreichend für die UI-Anforderungen (Label, Button, Text, Treeview). Keine Node.js/Browser-Abhängigkeit.

**Alternativen erwogen:**
- *PyQt6/PySide6:* Bessere Widgets, aber zusätzliche Abhängigkeit (~50 MB).
- *Streamlit/Flask+Browser:* Benötigt laufenden Server, Browser-Tab immer offen.
- *Electron:* Node.js-Dependency, komplexer Build-Prozess.

**Konsequenzen:**
- (+) Keine zusätzliche Dependency
- (+) Native macOS-Look via ttk
- (-) Tkinter ist threading-unfriendly — UI-Thread blockiert bei synchronen Calls (mehrere HIGH-Findings)
- (-) Race Conditions bei `_proc`-Zugriff aus Background-Thread (HIGH-Finding)
- (-) `messagebox` Import fehlt in `status.py` (HIGH-Finding — NameError bei Guard)

**Verwandte ADRs:** ADR-005
