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
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.willhabenanalyse.pipeline.plist"
LAUNCHD_LABEL = "com.willhabenanalyse.pipeline"

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

        ttk.Label(f, text="Automatischer Zeitplan (launchd)", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(15, 10), padx=15, sticky="w")

        # Uhrzeit
        ttk.Label(f, text="Startzeit (HH:MM):").grid(row=1, column=0, sticky="w", padx=15, pady=5)
        time_frame = ttk.Frame(f)
        time_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)
        self.sched_hour = tk.IntVar(value=sched.get("hour", 0))
        self.sched_minute = tk.IntVar(value=sched.get("minute", 0))
        ttk.Spinbox(time_frame, from_=0, to=23, textvariable=self.sched_hour, width=4,
                    format="%02.0f").pack(side="left")
        ttk.Label(time_frame, text=":").pack(side="left")
        ttk.Spinbox(time_frame, from_=0, to=59, textvariable=self.sched_minute, width=4,
                    format="%02.0f").pack(side="left")

        # Intervall-Dropdown
        ttk.Label(f, text="Intervall:").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        self.sched_interval = tk.StringVar(value=sched.get("interval", "Täglich"))
        interval_cb = ttk.Combobox(
            f,
            textvariable=self.sched_interval,
            values=["Täglich", "Alle 12h", "Alle 6h", "Manuell"],
            state="readonly",
            width=12,
        )
        interval_cb.grid(row=2, column=1, sticky="w", padx=5)

        # AN/AUS Checkbox
        launchd_active = self._launchd_is_loaded()
        self.launchd_enabled = tk.BooleanVar(value=launchd_active)
        ttk.Checkbutton(
            f,
            text="launchd Service aktiv",
            variable=self.launchd_enabled,
            command=self._toggle_launchd,
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=15, pady=10)

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=4, column=0, columnspan=3, sticky="w", padx=15, pady=5)
        ttk.Button(btn_frame, text="Einstellungen speichern & neu laden",
                   command=self._save_schedule).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Jetzt manuell ausführen",
                   command=self._run_scrape_now).pack(side="left", padx=5)

        self.status_label = ttk.Label(f, text="", foreground="green")
        self.status_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=15)

    def _launchd_is_loaded(self) -> bool:
        try:
            result = subprocess.run(
                ["launchctl", "list", LAUNCHD_LABEL],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def _write_plist(self, hour: int, minute: int, interval: str) -> None:
        """Schreibt die plist-Datei mit den aktuellen Zeitplan-Einstellungen."""
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

        if interval == "Täglich":
            calendar_entries = [{"Hour": hour, "Minute": minute}]
        elif interval == "Alle 12h":
            calendar_entries = [
                {"Hour": hour, "Minute": minute},
                {"Hour": (hour + 12) % 24, "Minute": minute},
            ]
        elif interval == "Alle 6h":
            calendar_entries = [
                {"Hour": (hour + i * 6) % 24, "Minute": minute}
                for i in range(4)
            ]
        else:
            # Manuell: kein automatischer Zeitplan (kein StartCalendarInterval)
            calendar_entries = []

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
            '<plist version="1.0">',
            '<dict>',
            '    <key>Label</key>',
            f'    <string>{LAUNCHD_LABEL}</string>',
            '    <key>ProgramArguments</key>',
            '    <array>',
            '        <string>/opt/homebrew/bin/python3</string>',
            '        <string>/Users/Boti/WillhabenAnalyse/main.py</string>',
            '        <string>--once</string>',
            '    </array>',
            '    <key>WorkingDirectory</key>',
            '    <string>/Users/Boti/WillhabenAnalyse</string>',
        ]

        if calendar_entries:
            if len(calendar_entries) == 1:
                e = calendar_entries[0]
                lines += [
                    '    <key>StartCalendarInterval</key>',
                    '    <dict>',
                    '        <key>Hour</key>',
                    f'        <integer>{e["Hour"]}</integer>',
                    '        <key>Minute</key>',
                    f'        <integer>{e["Minute"]}</integer>',
                    '    </dict>',
                ]
            else:
                lines += ['    <key>StartCalendarInterval</key>', '    <array>']
                for e in calendar_entries:
                    lines += [
                        '        <dict>',
                        '            <key>Hour</key>',
                        f'            <integer>{e["Hour"]}</integer>',
                        '            <key>Minute</key>',
                        f'            <integer>{e["Minute"]}</integer>',
                        '        </dict>',
                    ]
                lines.append('    </array>')

        lines += [
            '    <key>StandardOutPath</key>',
            '    <string>/Users/Boti/WillhabenAnalyse/logs/launchd_stdout.log</string>',
            '    <key>StandardErrorPath</key>',
            '    <string>/Users/Boti/WillhabenAnalyse/logs/launchd_stderr.log</string>',
            '    <key>EnvironmentVariables</key>',
            '    <dict>',
            '        <key>PATH</key>',
            '        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>',
            '        <key>OLLAMA_MODELS</key>',
            '        <string>/Volumes/MacMiniMich/KI</string>',
            '    </dict>',
            '    <key>Disabled</key>',
            '    <false/>',
            '</dict>',
            '</plist>',
            '',
        ]
        PLIST_PATH.write_text("\n".join(lines), encoding="utf-8")

    def _reload_launchd(self) -> None:
        """Entlädt und lädt den launchd Service neu."""
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                       capture_output=True)
        subprocess.run(["launchctl", "load", str(PLIST_PATH)],
                       capture_output=True)

    def _toggle_launchd(self) -> None:
        """Aktiviert oder deaktiviert den launchd Service."""
        if self.launchd_enabled.get():
            result = subprocess.run(
                ["launchctl", "load", str(PLIST_PATH)],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self.status_label.config(text="launchd Service aktiviert.", foreground="green")
            else:
                self.status_label.config(
                    text=f"Fehler beim Aktivieren: {result.stderr.strip()}", foreground="red")
                self.launchd_enabled.set(False)
        else:
            subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
            self.status_label.config(text="launchd Service deaktiviert.", foreground="orange")

    def _save_schedule(self):
        hour = self.sched_hour.get()
        minute = self.sched_minute.get()
        interval = self.sched_interval.get()

        self._write_plist(hour, minute, interval)

        self.config_data["schedule"] = {
            "hour": hour,
            "minute": minute,
            "interval": interval,
            "enabled": self.launchd_enabled.get(),
        }
        save_config(self.config_data)

        # Service neu laden wenn aktiv
        if self.launchd_enabled.get():
            self._reload_launchd()
            self.status_label.config(
                text=f"Gespeichert & neu geladen ({interval}, {hour:02d}:{minute:02d}).",
                foreground="green"
            )
        else:
            self.status_label.config(text="Gespeichert (Service inaktiv).", foreground="green")

    def _run_scrape_now(self):
        self.status_label.config(text="Starte Pipeline im Hintergrund …", foreground="blue")
        def _run():
            try:
                subprocess.Popen(
                    ["/opt/homebrew/bin/python3", str(BASE_DIR / "main.py"), "--once"],
                    cwd=str(BASE_DIR),
                )
                self.status_label.config(text="Pipeline gestartet (läuft im Hintergrund).", foreground="green")
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
