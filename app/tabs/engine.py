"""
engine.py — D1: Modell-Auswahl + Test-Batch Tab

Class EngineTab(ttk.Frame):
  Allows selecting parser model, max listings, and running a test batch.
"""
import sys
import threading
from pathlib import Path
from typing import Callable

try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk, messagebox
    _TK_BASE = ttk.Frame
except ModuleNotFoundError:  # headless / no _tkinter compiled
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    scrolledtext = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    _TK_BASE = object  # type: ignore[assignment,misc]

from app.backend import subprocess_runner


class EngineTab(_TK_BASE):  # type: ignore[misc]
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

    def build(self) -> None:
        """Build the UI widgets."""
        # ---- Header ----
        ttk.Label(self, text="Parser-Engine & Modell", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10)
        )

        # ---- Modell Combobox ----
        ttk.Label(self, text="Modell:").grid(row=1, column=0, sticky="w", padx=15, pady=5)
        self._model_var = tk.StringVar(
            value=self.config_data.get("model", "gemma3:27b")
        )
        model_cb = ttk.Combobox(
            self,
            textvariable=self._model_var,
            values=["gemma3:27b", "gemma4:26b", "gemma4:latest"],
            state="readonly",
            width=20,
        )
        model_cb.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # ---- Max. Anzeigen Spinbox ----
        ttk.Label(self, text="Max. Anzeigen:").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        max_listings = self.config_data.get("max_listings")
        self._max_listings_var = tk.StringVar(
            value="Alle" if max_listings is None else str(max_listings)
        )
        max_sb = ttk.Spinbox(
            self,
            from_=1,
            to=9999,
            textvariable=self._max_listings_var,
            values=["Alle"] + [str(i) for i in range(1, 10000)],
            width=10,
        )
        max_sb.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # ---- Test-Batch Row ----
        ttk.Label(self, text="Test-Batch N:").grid(row=3, column=0, sticky="w", padx=15, pady=5)
        self._test_batch_var = tk.StringVar(value="50")
        ttk.Spinbox(
            self,
            from_=1,
            to=500,
            textvariable=self._test_batch_var,
            width=10,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(self, text="Test starten", command=self._start_test).grid(
            row=3, column=2, sticky="w", padx=5, pady=5
        )

        # ---- Save Button ----
        ttk.Button(
            self, text="Einstellungen speichern", command=self._save_settings
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 5))

        # ---- Log Area ----
        ttk.Label(self, text="Test-Ausgabe:").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 2)
        )
        self._log = scrolledtext.ScrolledText(
            self,
            height=18,
            state="disabled",
            font=("Courier", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            wrap="none",
        )
        self._log.grid(
            row=6, column=0, columnspan=3, sticky="nsew", padx=15, pady=(0, 10)
        )
        self.columnconfigure(2, weight=1)
        self.rowconfigure(6, weight=1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_log(self, line: str) -> None:
        """Append a line to the log ScrolledText (thread-safe via after)."""
        self._log.after(0, self._do_append_log, line)

    def _do_append_log(self, line: str) -> None:
        self._log.config(state="normal")
        self._log.insert("end", line + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _start_test(self) -> None:
        """Start a test pipeline run in a background daemon thread."""
        try:
            n = int(self._test_batch_var.get())
        except ValueError:
            messagebox.showerror("Fehler", "Ungültige Test-Batch-Anzahl.")
            return

        self._append_log(f"--- Test-Batch gestartet (N={n}) ---")

        def _run() -> None:
            python_path = sys.executable
            self._proc = subprocess_runner.start_pipeline(
                python_path=python_path,
                project_dir=str(self.base_dir),
                parser_version=self.config_data.get("parser_version", "v2"),
                model=self._model_var.get(),
                max_listings=n,
                log_callback=self._append_log,
            )
            self._proc.wait()
            rc = self._proc.returncode
            self._append_log(f"--- Test-Batch beendet (exit code {rc}) ---")

        threading.Thread(target=_run, daemon=True).start()

    def _save_settings(self) -> None:
        """Save model and max_listings to config."""
        self.config_data["model"] = self._model_var.get()
        raw = self._max_listings_var.get().strip()
        self.config_data["max_listings"] = None if raw == "Alle" else int(raw)
        self.save_config_fn(self.config_data)
        messagebox.showinfo("Gespeichert", "Einstellungen wurden gespeichert.")

    # ------------------------------------------------------------------
    # Public helpers for unit tests (no Tk needed)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_max_listings(raw: str) -> int | None:
        """Convert the raw spinbox string to the config value.

        Returns None for 'Alle', else int.
        """
        return None if raw.strip() == "Alle" else int(raw.strip())
