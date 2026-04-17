"""
zeitplan.py — D2: Automatisierung mit launchd Tab

Class ZeitplanTab(ttk.Frame):
  Configure and manage launchd scheduling for the pipeline.
"""
import sys
from pathlib import Path
from typing import Callable

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    _TK_BASE = ttk.Frame
except ModuleNotFoundError:
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    _TK_BASE = object  # type: ignore[assignment,misc]

from app.backend import launchd_manager


class ZeitplanTab(_TK_BASE):  # type: ignore[misc]
    def __init__(
        self,
        parent: tk.Widget,
        config_data: dict,
        save_config_fn: Callable,
        base_dir: Path,
    ) -> None:
        super().__init__(parent)
        self.config_data = config_data
        self.save_config_fn = save_config_fn
        self.base_dir = base_dir

    def build(self) -> None:
        """Build the UI widgets."""
        launchd_cfg = self.config_data.get("launchd", {})

        # ---- Header ----
        ttk.Label(
            self, text="Automatischer Zeitplan (launchd)", font=("", 13, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10))

        # ---- Stunde ----
        ttk.Label(self, text="Uhrzeit (Stunde):").grid(
            row=1, column=0, sticky="w", padx=15, pady=5
        )
        self._hour_var = tk.StringVar(value=str(launchd_cfg.get("hour", 2)))
        ttk.Spinbox(self, from_=0, to=23, textvariable=self._hour_var, width=6).grid(
            row=1, column=1, sticky="w", padx=5, pady=5
        )

        # ---- Minute ----
        ttk.Label(self, text="Minute:").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        self._minute_var = tk.StringVar(value=str(launchd_cfg.get("minute", 0)))
        ttk.Spinbox(self, from_=0, to=59, textvariable=self._minute_var, width=6).grid(
            row=2, column=1, sticky="w", padx=5, pady=5
        )

        # ---- launchd Label Entry ----
        ttk.Label(self, text="launchd Label:").grid(
            row=3, column=0, sticky="w", padx=15, pady=5
        )
        self._label_var = tk.StringVar(
            value=launchd_cfg.get("label", "com.willhaben.analyse")
        )
        ttk.Entry(self, textvariable=self._label_var, width=30).grid(
            row=3, column=1, columnspan=2, sticky="w", padx=5, pady=5
        )

        # ---- Aktiviert Checkbox ----
        self._enabled_var = tk.BooleanVar(
            value=self.config_data.get("schedule", {}).get("enabled", False)
        )
        ttk.Checkbutton(
            self,
            text="Aktiviert (launchd installieren/deinstallieren)",
            variable=self._enabled_var,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=15, pady=8)

        # ---- Button row ----
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=15, pady=5)
        ttk.Button(btn_frame, text="launchd installieren", command=self._install).pack(
            side="left", padx=5
        )
        ttk.Button(
            btn_frame, text="launchd deinstallieren", command=self._uninstall
        ).pack(side="left", padx=5)

        # ---- Status label ----
        self._status_label = ttk.Label(self, text="", foreground="gray")
        self._status_label.grid(
            row=6, column=0, columnspan=3, sticky="w", padx=15, pady=5
        )
        self._update_status_label()

        # ---- Save button ----
        ttk.Button(
            self, text="Einstellungen speichern", command=self._save_settings
        ).grid(row=7, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 5))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_label(self) -> str:
        return self._label_var.get().strip()

    def _update_status_label(self) -> None:
        label = self._current_label()
        if launchd_manager.is_installed(label):
            self._status_label.config(text="Status: installiert", foreground="green")
        else:
            self._status_label.config(
                text="Status: nicht installiert", foreground="gray"
            )

    def _install(self) -> None:
        label = self._current_label()
        try:
            hour = int(self._hour_var.get())
            minute = int(self._minute_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Stunden- oder Minutenangabe.")
            return

        # Prefer the project venv python; fall back to the running interpreter
        venv_python = str(self.base_dir / ".venv" / "bin" / "python3")
        if Path(venv_python).exists():
            python_path = venv_python
        else:
            python_path = sys.executable  # fallback

        xml = launchd_manager.generate_plist(
            label=label,
            python_path=python_path,
            project_dir=str(self.base_dir),
            model=self.config_data.get("model", "gemma3:27b"),
            max_listings=self.config_data.get("max_listings"),
            hour=hour,
            minute=minute,
        )
        ok, msg = launchd_manager.install_plist(xml, label)
        if ok:
            messagebox.showinfo("Installiert", msg)
        else:
            messagebox.showerror("Fehler", msg)
        self._update_status_label()

    def _uninstall(self) -> None:
        label = self._current_label()
        ok, msg = launchd_manager.uninstall_plist(label)
        if ok:
            messagebox.showinfo("Deinstalliert", msg)
        else:
            messagebox.showerror("Fehler", msg)
        self._update_status_label()

    def _save_settings(self) -> None:
        """Persist launchd schedule settings to config."""
        try:
            hour = int(self._hour_var.get())
            minute = int(self._minute_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Stunden- oder Minutenangabe.")
            return

        label = self._current_label()
        self.config_data.setdefault("launchd", {})
        self.config_data["launchd"]["label"] = label
        self.config_data["launchd"]["hour"] = hour
        self.config_data["launchd"]["minute"] = minute
        self.config_data.setdefault("schedule", {})
        self.config_data["schedule"]["enabled"] = self._enabled_var.get()
        self.save_config_fn(self.config_data)
        messagebox.showinfo("Gespeichert", "Zeitplan-Einstellungen wurden gespeichert.")

    # ------------------------------------------------------------------
    # Public helper for unit tests
    # ------------------------------------------------------------------

    @staticmethod
    def build_launchd_config(label: str, hour: int, minute: int, enabled: bool) -> dict:
        """Return the config dict fragment that _save_settings would produce.

        Used in unit tests without needing a Tk root.
        """
        return {
            "launchd": {"label": label, "hour": hour, "minute": minute},
            "schedule": {"enabled": enabled},
        }
