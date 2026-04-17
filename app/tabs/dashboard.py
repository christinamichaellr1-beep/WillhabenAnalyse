"""
dashboard.py — D4: Marktanalyse Tab

Class DashboardTab(ttk.Frame):
  Loads aggregated Excel data and displays it in a Treeview with filter/sort.
"""
import math
from pathlib import Path
from typing import Callable

try:
    import tkinter as tk
    from tkinter import filedialog, ttk, messagebox
    _TK_BASE = ttk.Frame
except ModuleNotFoundError:
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    _TK_BASE = object  # type: ignore[assignment,misc]

from app.backend import dashboard_aggregator

_COLUMNS = [
    "Event", "Kategorie", "Datum", "Venue", "Stadt",
    "Privat_Anzahl", "Privat_Min", "Privat_Avg", "Privat_Max",
    "Haendler_Anzahl", "Haendler_Min", "Haendler_Avg", "Haendler_Max",
    "OVP", "Marge_Haendler_Pct", "Marge_Privat_Pct",
]


class DashboardTab(_TK_BASE):  # type: ignore[misc]
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
        self._df = None  # holds the aggregated DataFrame
        self._sort_col: str | None = None
        self._filter_text: str = ""

    def build(self) -> None:
        """Build the UI widgets."""
        # ---- Header ----
        ttk.Label(self, text="Marktanalyse", font=("", 13, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(15, 10)
        )

        # ---- Filter row ----
        filter_frame = ttk.Frame(self)
        filter_frame.grid(row=1, column=0, columnspan=4, sticky="w", padx=15, pady=5)
        ttk.Label(filter_frame, text="Suche Event:").pack(side="left")
        self._search_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self._search_var, width=30).pack(
            side="left", padx=5
        )
        ttk.Button(filter_frame, text="Filtern", command=self._apply_filters).pack(
            side="left", padx=5
        )

        # ---- Sort row ----
        sort_frame = ttk.Frame(self)
        sort_frame.grid(row=2, column=0, columnspan=4, sticky="w", padx=15, pady=5)
        ttk.Label(sort_frame, text="Sortierung:").pack(side="left")
        self._sort_var = tk.StringVar()
        ttk.Combobox(
            sort_frame,
            textvariable=self._sort_var,
            values=_COLUMNS,
            state="readonly",
            width=22,
        ).pack(side="left", padx=5)
        ttk.Button(sort_frame, text="Sortieren", command=self._sort_and_apply).pack(
            side="left", padx=5
        )

        # ---- Treeview with scrollbars ----
        tree_frame = ttk.Frame(self)
        tree_frame.grid(
            row=3, column=0, columnspan=4, sticky="nsew", padx=15, pady=5
        )
        self.rowconfigure(3, weight=1)
        self.columnconfigure(3, weight=1)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=_COLUMNS,
            show="headings",
            selectmode="browse",
        )
        for col in _COLUMNS:
            self._tree.heading(col, text=col)
            width = 140 if col == "Event" else 80
            self._tree.column(col, width=width, minwidth=50, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # ---- Button row ----
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=4, sticky="w", padx=15, pady=5)
        ttk.Button(btn_frame, text="Laden", command=self._load_data).pack(
            side="left", padx=5
        )
        ttk.Button(btn_frame, text="CSV Export", command=self._export_csv).pack(
            side="left", padx=5
        )

        # ---- Status label ----
        self._status_label = ttk.Label(self, text="Keine Daten geladen.")
        self._status_label.grid(
            row=5, column=0, columnspan=4, sticky="w", padx=15, pady=5
        )

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        export_path = Path(self.config_data.get("export_path", ""))
        if not export_path.is_absolute():
            export_path = self.base_dir / export_path
        self._status_label.config(text=f"Lade {export_path} …")
        try:
            df = dashboard_aggregator.load_excel(export_path)
            self._df = dashboard_aggregator.aggregate(df)
            self._apply_filters()
            rows = len(self._df) if self._df is not None else 0
            self._status_label.config(text=f"{rows} Events geladen.")
        except Exception as exc:
            self._status_label.config(text=f"Fehler: {exc}")
            messagebox.showerror("Fehler beim Laden", str(exc))

    def _apply_filters(self) -> None:
        """Filter and sort self._df, then populate the Treeview."""
        if self._df is None:
            return

        df = self._df.copy()
        search = self._search_var.get().strip().lower()
        if search:
            mask = df["Event"].astype(str).str.lower().str.contains(search, na=False)
            df = df[mask]

        sort_col = self._sort_var.get()
        if sort_col and sort_col in df.columns:
            try:
                df = df.sort_values(by=sort_col, ascending=True)
            except Exception:
                pass

        self._populate_tree(df)

    def _sort_and_apply(self) -> None:
        self._apply_filters()

    def _populate_tree(self, df) -> None:
        """Clear and re-insert rows into the Treeview."""
        for row_id in self._tree.get_children():
            self._tree.delete(row_id)

        if df is None or df.empty:
            return

        for _, row in df.iterrows():
            values = []
            for col in _COLUMNS:
                val = row.get(col, "")
                if isinstance(val, float):
                    if math.isnan(val):
                        values.append("")
                    else:
                        values.append(f"{val:.2f}")
                else:
                    values.append("" if val is None else str(val))
            self._tree.insert("", "end", values=values)

    def _export_csv(self) -> None:
        if self._df is None or self._df.empty:
            messagebox.showwarning("Keine Daten", "Bitte zuerst Daten laden.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Alle Dateien", "*.*")],
            initialfile="marktanalyse.csv",
        )
        if not path:
            return
        try:
            dashboard_aggregator.export_csv(self._df, Path(path))
            self._status_label.config(text=f"CSV exportiert: {path}")
            messagebox.showinfo("Exportiert", f"CSV gespeichert:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export-Fehler", str(exc))

    # ------------------------------------------------------------------
    # Public helper for unit tests (pure logic, no Tk needed)
    # ------------------------------------------------------------------

    @staticmethod
    def filter_df(df, search: str = "", sort_col: str = ""):
        """Apply filter + sort to a DataFrame without any Tk interaction.

        Used in unit tests without needing a Tk root.
        """
        if df is None or df.empty:
            return df

        result = df.copy()
        if search:
            mask = result["Event"].astype(str).str.lower().str.contains(
                search.lower(), na=False
            )
            result = result[mask]
        if sort_col and sort_col in result.columns:
            try:
                result = result.sort_values(by=sort_col, ascending=True)
            except Exception:
                pass
        return result
