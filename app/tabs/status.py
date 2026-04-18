"""
status.py — D3: Live-Monitoring Tab

Class StatusTab(ttk.Frame):
  Polls .willhaben_status.json and displays pipeline progress in real time.
"""
import sys
import threading
from pathlib import Path
from typing import Callable

try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk
    _TK_BASE = ttk.Frame
except ModuleNotFoundError:
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    scrolledtext = None  # type: ignore[assignment]
    _TK_BASE = object  # type: ignore[assignment,misc]

from app.backend import status_monitor, subprocess_runner


class StatusTab(_TK_BASE):  # type: ignore[misc]
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
        self._proc = None
        self._after_id = None

    def build(self) -> None:
        """Build the UI widgets."""
        # ---- Header ----
        ttk.Label(self, text="Live-Status", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10)
        )

        # ---- Progress label ----
        self._progress_label = ttk.Label(self, text="Fortschritt: —")
        self._progress_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=15, pady=3)

        # ---- Model label ----
        self._model_label = ttk.Label(self, text="Modell: —")
        self._model_label.grid(row=2, column=0, columnspan=3, sticky="w", padx=15, pady=3)

        # ---- Status label ----
        self._status_label = ttk.Label(self, text="Status: —", foreground="gray")
        self._status_label.grid(row=3, column=0, columnspan=3, sticky="w", padx=15, pady=3)

        # ---- Average duration ----
        self._duration_label = ttk.Label(self, text="Ø Dauer: —")
        self._duration_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=15, pady=3)

        # ---- Errors label ----
        self._errors_label = ttk.Label(self, text="Fehler: —")
        self._errors_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=15, pady=3)

        # ---- Last error ScrolledText ----
        ttk.Label(self, text="Letzter Fehler:").grid(
            row=6, column=0, columnspan=3, sticky="w", padx=15, pady=(8, 2)
        )
        self._error_text = scrolledtext.ScrolledText(
            self,
            height=6,
            state="disabled",
            font=("Courier", 9),
            wrap="word",
        )
        self._error_text.grid(
            row=7, column=0, columnspan=3, sticky="ew", padx=15, pady=(0, 8)
        )
        self.columnconfigure(2, weight=1)

        # ---- Button row ----
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=3, sticky="w", padx=15, pady=5)
        ttk.Button(btn_frame, text="Aktualisieren", command=self._refresh).pack(
            side="left", padx=5
        )
        ttk.Button(
            btn_frame, text="Pipeline jetzt starten", command=self._start_pipeline
        ).pack(side="left", padx=5)

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Read status and update all UI labels. Schedules next auto-refresh if running."""
        status = status_monitor.read_status(self.base_dir)

        if status is None:
            self._progress_label.config(text="Fortschritt: Kein Status verfügbar")
            self._model_label.config(text="Modell: —")
            self._status_label.config(text="Status: Kein Status verfügbar", foreground="gray")
            self._duration_label.config(text="Ø Dauer: —")
            self._errors_label.config(text="Fehler: —")
            self._set_error_text("")
            return

        # Progress
        progress_str = status_monitor.format_progress(status)
        self._progress_label.config(text=f"Fortschritt: {progress_str}")

        # Model
        model = status.get("model", "—")
        self._model_label.config(text=f"Modell: {model}")

        # Status (coloured)
        st = status.get("status", "—")
        color = {"running": "green", "done": "blue", "error": "red"}.get(st, "gray")
        self._status_label.config(text=f"Status: {st}", foreground=color)

        # Avg duration
        avg = status_monitor.avg_duration_ms(status)
        avg_str = f"{avg:.0f} ms" if avg is not None else "—"
        self._duration_label.config(text=f"Ø Dauer: {avg_str}")

        # Errors
        errors = status.get("errors", 0)
        self._errors_label.config(text=f"Fehler: {errors}")

        # Last error text
        last_error = status.get("last_error", "")
        self._set_error_text(last_error or "")

        # Auto-refresh if still running
        if status_monitor.is_running(status):
            self._after_id = self.after(2000, self._refresh)

    def _set_error_text(self, text: str) -> None:
        self._error_text.config(state="normal")
        self._error_text.delete("1.0", "end")
        if text:
            self._error_text.insert("end", text)
        self._error_text.config(state="disabled")

    def _start_pipeline(self) -> None:
        """Start pipeline subprocess and kick off auto-refresh."""
        if self._proc is not None and subprocess_runner.is_running(self._proc):
            messagebox.showwarning("Läuft bereits", "Die Pipeline ist bereits aktiv.")
            return

        def _run() -> None:
            self._proc = subprocess_runner.start_pipeline(
                python_path=sys.executable,
                project_dir=str(self.base_dir),
                parser_version=self.config_data.get("parser_version", "v2"),
                model=self.config_data.get("model", "gemma3:27b"),
                max_listings=self.config_data.get("max_listings"),
            )

        threading.Thread(target=_run, daemon=True).start()
        # Begin auto-refresh immediately
        self.after(500, self._refresh)

    def destroy(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        super().destroy()

    # ------------------------------------------------------------------
    # Public helper for unit tests (pure logic, no Tk needed)
    # ------------------------------------------------------------------

    @staticmethod
    def status_to_display(status: dict | None) -> dict:
        """Convert a raw status dict (or None) into display strings.

        Returns a dict with keys: progress, model, status_text, status_color,
        avg_duration, errors, last_error.
        Used in unit tests without needing a Tk root.
        """
        if status is None:
            return {
                "progress": "Kein Status verfügbar",
                "model": "—",
                "status_text": "Kein Status verfügbar",
                "status_color": "gray",
                "avg_duration": "—",
                "errors": "—",
                "last_error": "",
            }

        avg = status_monitor.avg_duration_ms(status)
        avg_str = f"{avg:.0f} ms" if avg is not None else "—"
        st = status.get("status", "—")
        color = {"running": "green", "done": "blue", "error": "red"}.get(st, "gray")
        return {
            "progress": status_monitor.format_progress(status),
            "model": status.get("model", "—"),
            "status_text": st,
            "status_color": color,
            "avg_duration": avg_str,
            "errors": str(status.get("errors", 0)),
            "last_error": status.get("last_error", ""),
        }
