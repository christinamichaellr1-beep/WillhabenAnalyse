"""
WillhabenAnalyse GUI – tkinter, 5 Tabs.
Speichert Einstellungen in config.json.
"""
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path
import datetime

LAUNCHAGENT_LABEL = "com.willhabenanalyse.pipeline"
LAUNCHAGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHAGENT_LABEL}.plist"


def _launchagent_is_loaded() -> bool:
    """True wenn der LaunchAgent aktuell geladen ist."""
    try:
        result = subprocess.run(
            ["launchctl", "list", LAUNCHAGENT_LABEL],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "schedule": {
        "scrape_interval_minutes": 360,
        "enabled": False,
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
        self.geometry("900x650")
        self.resizable(True, True)
        self.config_data = load_config()
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_schedule  = ttk.Frame(notebook)
        self.tab_providers = ttk.Frame(notebook)
        self.tab_watchlist = ttk.Frame(notebook)
        self.tab_export    = ttk.Frame(notebook)
        self.tab_log       = ttk.Frame(notebook)

        notebook.add(self.tab_schedule,  text="Zeitplan")
        notebook.add(self.tab_providers, text="Anbieter (OVP)")
        notebook.add(self.tab_watchlist, text="Watchlist")
        notebook.add(self.tab_export,    text="Export")
        notebook.add(self.tab_log,       text="Log")

        self._build_schedule_tab()
        self._build_providers_tab()
        self._build_watchlist_tab()
        self._build_export_tab()
        self._build_log_tab()

    # ---- Tab: Zeitplan ----

    def _build_schedule_tab(self):
        f = self.tab_schedule
        sched = self.config_data.get("schedule", DEFAULT_CONFIG["schedule"])

        ttk.Label(f, text="Automatischer Zeitplan", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(15, 10), padx=15, sticky="w")

        ttk.Label(f, text="Scraping-Intervall (Minuten):").grid(row=1, column=0, sticky="w", padx=15, pady=5)
        self.scrape_interval = tk.IntVar(value=sched.get("scrape_interval_minutes", 120))
        ttk.Spinbox(f, from_=15, to=1440, textvariable=self.scrape_interval, width=8).grid(
            row=1, column=1, sticky="w", padx=5)

        ttk.Label(f, text="OVP-Check-Intervall (Minuten):").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        self.ovp_interval = tk.IntVar(value=sched.get("ovp_interval_minutes", 60))
        ttk.Spinbox(f, from_=10, to=720, textvariable=self.ovp_interval, width=8).grid(
            row=2, column=1, sticky="w", padx=5)

        self.schedule_enabled = tk.BooleanVar(value=sched.get("enabled", False))
        ttk.Checkbutton(f, text="Scheduling aktiv", variable=self.schedule_enabled).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=15, pady=10)

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=4, column=0, columnspan=2, sticky="w", padx=15, pady=5)
        ttk.Button(btn_frame, text="Jetzt scrapen", command=self._run_scrape_now).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Einstellungen speichern", command=self._save_schedule).pack(side="left", padx=5)

        self.status_label = ttk.Label(f, text="", foreground="green")
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=15)

        # ---- LaunchAgent AN/AUS ----
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=15, pady=(15, 8))

        ttk.Label(f, text="Tägliche Ausführung (launchd, 00:00)", font=("", 11, "bold")).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=15)

        la_btn_frame = ttk.Frame(f)
        la_btn_frame.grid(row=8, column=0, columnspan=2, sticky="w", padx=15, pady=5)
        self.la_on_btn = ttk.Button(la_btn_frame, text="AN", width=8, command=self._launchagent_on)
        self.la_on_btn.pack(side="left", padx=(0, 5))
        self.la_off_btn = ttk.Button(la_btn_frame, text="AUS", width=8, command=self._launchagent_off)
        self.la_off_btn.pack(side="left", padx=5)

        self.la_status_label = ttk.Label(f, text="")
        self.la_status_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=15)

        self._update_launchagent_status()

    def _save_schedule(self):
        self.config_data["schedule"] = {
            "scrape_interval_minutes": self.scrape_interval.get(),
            "ovp_interval_minutes": self.ovp_interval.get(),
            "enabled": self.schedule_enabled.get(),
        }
        save_config(self.config_data)
        self.status_label.config(text="Gespeichert.", foreground="green")

    def _update_launchagent_status(self):
        loaded = _launchagent_is_loaded()
        if loaded:
            self.la_status_label.config(text="Status: AKTIV (läuft täglich um 00:00)", foreground="green")
            self.la_on_btn.config(state="disabled")
            self.la_off_btn.config(state="normal")
        else:
            self.la_status_label.config(text="Status: INAKTIV", foreground="gray")
            self.la_on_btn.config(state="normal")
            self.la_off_btn.config(state="disabled")

    def _launchagent_on(self):
        if not LAUNCHAGENT_PLIST.exists():
            messagebox.showerror("Fehler", f"Plist nicht gefunden:\n{LAUNCHAGENT_PLIST}")
            return
        try:
            subprocess.run(
                ["launchctl", "load", str(LAUNCHAGENT_PLIST)],
                check=True, capture_output=True, text=True
            )
            self._update_launchagent_status()
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Fehler", f"launchctl load fehlgeschlagen:\n{exc.stderr}")

    def _launchagent_off(self):
        try:
            subprocess.run(
                ["launchctl", "unload", str(LAUNCHAGENT_PLIST)],
                check=True, capture_output=True, text=True
            )
            self._update_launchagent_status()
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Fehler", f"launchctl unload fehlgeschlagen:\n{exc.stderr}")

    def _run_scrape_now(self):
        self.status_label.config(text="Starte Pipeline …", foreground="blue")
        def _run():
            try:
                import sys
                sys.path.insert(0, str(BASE_DIR))
                import main as m
                m.run_pipeline(log_callback=self._append_log)
                self.status_label.config(text="Pipeline fertig.", foreground="green")
            except Exception as exc:
                self.status_label.config(text=f"Fehler: {exc}", foreground="red")
                self._append_log(f"FEHLER: {exc}")
        threading.Thread(target=_run, daemon=True).start()

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

    # ---- Tab: Export ----

    def _build_export_tab(self):
        f = self.tab_export
        ttk.Label(f, text="Excel-Export Einstellungen", font=("", 13, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10))

        path_frame = ttk.Frame(f)
        path_frame.pack(anchor="w", padx=15, pady=5, fill="x")
        ttk.Label(path_frame, text="Export-Pfad:").pack(side="left")
        self.export_path_var = tk.StringVar(value=self.config_data.get("export_path", ""))
        ttk.Entry(path_frame, textvariable=self.export_path_var, width=50).pack(side="left", padx=5)
        ttk.Button(path_frame, text="…", command=self._browse_export_path, width=3).pack(side="left")

        ttk.Button(f, text="Speichern", command=self._save_export).pack(anchor="w", padx=15, pady=10)
        ttk.Button(f, text="Abgelaufene Events archivieren", command=self._archive_now).pack(
            anchor="w", padx=15, pady=5)

        self.export_status = ttk.Label(f, text="", foreground="green")
        self.export_status.pack(anchor="w", padx=15)

    def _browse_export_path(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="willhaben_analyse.xlsx",
        )
        if path:
            self.export_path_var.set(path)

    def _save_export(self):
        self.config_data["export_path"] = self.export_path_var.get()
        save_config(self.config_data)
        self.export_status.config(text="Gespeichert.", foreground="green")

    def _archive_now(self):
        try:
            import sys
            sys.path.insert(0, str(BASE_DIR))
            from export.excel_writer import archive_expired
            path = Path(self.export_path_var.get())
            n = archive_expired(path)
            self.export_status.config(text=f"{n} Events archiviert.", foreground="green")
        except Exception as exc:
            self.export_status.config(text=f"Fehler: {exc}", foreground="red")

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
