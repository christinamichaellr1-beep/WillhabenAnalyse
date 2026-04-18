"""
WillhabenAnalyse GUI – tkinter, 7 Tabs (v2.1).
Speichert Einstellungen in config.json.
"""
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
import datetime

from app.tabs.engine import EngineTab
from app.tabs.zeitplan import ZeitplanTab
from app.tabs.status import StatusTab
from app.tabs.dashboard import DashboardTab

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "schedule": {
        # Kept for main.py daemon mode — GUI no longer shows schedule widgets
        "scrape_interval_minutes": 360,
    },
    # Such-URL-Templates: {event} wird durch den Event-Namen ersetzt
    "ovp_search_urls": [
        "https://www.oeticket.com/search?q={event}",
        "https://www.myticket.at/search?q={event}",
        "https://www.konzerthaus.at/suche?q={event}",
    ],
    # Format pro Eintrag: {event_name, ovp_preis (optional), ovp_link (optional)}
    "watchlist": [],
    "export_path": str(BASE_DIR / "data" / "willhaben_markt.xlsx"),
    "log_level": "INFO",
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Haupt-App
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WillhabenAnalyse")
        self.geometry("900x680")
        self.resizable(True, True)
        self.config_data = load_config()
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- New tabs from app/tabs/ ----
        tab_engine = EngineTab(notebook, self.config_data, save_config, BASE_DIR)
        tab_engine.build()
        notebook.add(tab_engine, text="Engine")

        tab_zeitplan = ZeitplanTab(notebook, self.config_data, save_config, BASE_DIR)
        tab_zeitplan.build()
        notebook.add(tab_zeitplan, text="Zeitplan")

        tab_status = StatusTab(notebook, self.config_data, save_config, BASE_DIR)
        tab_status.build()
        notebook.add(tab_status, text="Status")

        tab_dashboard = DashboardTab(notebook, self.config_data, save_config, BASE_DIR)
        tab_dashboard.build()
        notebook.add(tab_dashboard, text="Dashboard")

        # ---- Existing tabs (unchanged logic, now plain ttk.Frame in notebook) ----
        self.tab_providers = ttk.Frame(notebook)
        notebook.add(self.tab_providers, text="Anbieter (OVP)")
        self._build_providers_tab()

        self.tab_watchlist = ttk.Frame(notebook)
        notebook.add(self.tab_watchlist, text="Watchlist")
        self._build_watchlist_tab()

        self.tab_log = ttk.Frame(notebook)
        notebook.add(self.tab_log, text="Log")
        self._build_log_tab()

    # ---- Tab: Anbieter ----

    def _build_providers_tab(self):
        f = self.tab_providers
        ttk.Label(
            f,
            text="Such-URL-Templates (eine pro Zeile). {event} wird durch den Event-Namen ersetzt.",
            font=("", 10),
        ).pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(
            f,
            text="Beispiel: https://www.oeticket.com/search?q={event}",
            foreground="gray",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.providers_text = scrolledtext.ScrolledText(f, height=18, wrap="none", font=("Courier", 10))
        self.providers_text.pack(fill="both", expand=True, padx=10, pady=5)

        for url in self.config_data.get("ovp_search_urls", DEFAULT_CONFIG["ovp_search_urls"]):
            self.providers_text.insert("end", url + "\n")

        btn_frame = ttk.Frame(f)
        btn_frame.pack(anchor="w", padx=10, pady=5)
        ttk.Button(btn_frame, text="Speichern", command=self._save_providers).pack(side="left", padx=5)

    def _save_providers(self):
        content = self.providers_text.get("1.0", "end").strip()
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        self.config_data["ovp_search_urls"] = urls
        save_config(self.config_data)
        messagebox.showinfo("Gespeichert", f"{len(urls)} Anbieter-URLs gespeichert.")

    # ---- Tab: Watchlist ----

    def _build_watchlist_tab(self):
        f = self.tab_watchlist
        ttk.Label(
            f,
            text="Watchlist — ein Event pro Zeile:",
            font=("", 10, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(
            f,
            text="Format: Event-Name | OVP: 89.90 | Link: https://...",
            foreground="gray",
        ).pack(anchor="w", padx=10)
        ttk.Label(
            f,
            text="OVP und Link sind optional. Direktlink überspringt die automatische Suche.",
            foreground="gray",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self.watchlist_text = scrolledtext.ScrolledText(f, height=18, wrap="none", font=("Courier", 10))
        self.watchlist_text.pack(fill="both", expand=True, padx=10, pady=5)

        for w in self.config_data.get("watchlist", []):
            parts = [w.get("event_name", "")]
            if w.get("ovp_preis"):
                parts.append(f"OVP: {w['ovp_preis']}")
            if w.get("ovp_link"):
                parts.append(f"Link: {w['ovp_link']}")
            self.watchlist_text.insert("end", " | ".join(parts) + "\n")

        ttk.Button(f, text="Speichern", command=self._save_watchlist).pack(anchor="w", padx=10, pady=5)

    def _save_watchlist(self):
        content = self.watchlist_text.get("1.0", "end").strip()
        watchlist = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            event_name = parts[0].strip()
            if not event_name:
                continue
            entry: dict = {"event_name": event_name}
            for part in parts[1:]:
                part = part.strip()
                if part.upper().startswith("OVP:"):
                    try:
                        entry["ovp_preis"] = float(part[4:].strip().replace(",", "."))
                    except ValueError:
                        pass
                elif part.upper().startswith("LINK:"):
                    entry["ovp_link"] = part[5:].strip()
            watchlist.append(entry)
        self.config_data["watchlist"] = watchlist
        save_config(self.config_data)
        messagebox.showinfo("Gespeichert", f"{len(watchlist)} Watchlist-Einträge gespeichert.")

    # ---- Tab: Log ----

    def _build_log_tab(self):
        f = self.tab_log
        ttk.Label(f, text="Protokoll", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        self.log_text = scrolledtext.ScrolledText(f, height=28, state="disabled",
                                                   font=("Courier", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)
        ttk.Button(f, text="Log leeren", command=self._clear_log).pack(anchor="w", padx=10, pady=5)

    def _append_log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_text.config(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
