#!/usr/bin/env python3
# Copyright (c) 2026 Jongsu Lim
# SPDX-License-Identifier: MIT
"""Solution preparation calculator for perovskite and organic solar cells.

Run:  python3 solution_calculator.py
"""

from __future__ import annotations

import csv
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import chem
from calc import (
    DOPANT_UNITS,
    CalcError,
    Recipe,
    dilution,
    from_stock,
    mgml_to_molar,
    molar_to_mgml,
    opv_recipe,
    perovskite_recipe,
    transport_recipe,
)

__author__ = "Jongsu Lim"
__copyright__ = "Copyright (c) 2026 Jongsu Lim"
__license__ = "MIT"
__version__ = "1.0"

APP_NAME = "Solution Preparation Calculator"
COPYRIGHT = "© 2026 Jongsu Lim"
REPO_URL = "https://github.com/jongsu-king/perovskite-opv-solution-calculator"

APP_DIR = Path(__file__).resolve().parent
LIB_PATH = APP_DIR / "library.json"

A_CATIONS = ["MA", "FA", "Cs", "Rb", "GA", "PEA", "BA", "OA", "K"]
B_CATIONS = ["Pb", "Sn", "Ge"]
HALIDES = ["I", "Br", "Cl"]

PVK_PRESETS: dict[str, dict] = {
    "MAPbI3": {"a": [("MA", 1)], "b": [("Pb", 1)], "x": [("I", 3)]},
    "FAPbI3": {"a": [("FA", 1)], "b": [("Pb", 1)], "x": [("I", 3)]},
    "CsPbI3": {"a": [("Cs", 1)], "b": [("Pb", 1)], "x": [("I", 3)]},
    "CsPbBr3": {"a": [("Cs", 1)], "b": [("Pb", 1)], "x": [("Br", 3)]},
    "MAPbI3 + 30 mol% MACl": {
        "a": [("MA", 1)], "b": [("Pb", 1)], "x": [("I", 3)],
        "additives": [("MACl", 30)],
    },
    "FA0.83MA0.17Pb(I0.83Br0.17)3": {
        "a": [("FA", 0.83), ("MA", 0.17)], "b": [("Pb", 1)],
        "x": [("I", 2.49), ("Br", 0.51)],
    },
    "Cs0.05FA0.79MA0.16Pb(I0.83Br0.17)3 (triple cation)": {
        "a": [("Cs", 0.05), ("FA", 0.79), ("MA", 0.16)], "b": [("Pb", 1)],
        "x": [("I", 2.49), ("Br", 0.51)],
    },
    "Cs0.17FA0.83Pb(I0.83Br0.17)3": {
        "a": [("Cs", 0.17), ("FA", 0.83)], "b": [("Pb", 1)],
        "x": [("I", 2.49), ("Br", 0.51)],
    },
    "FASnI3": {"a": [("FA", 1)], "b": [("Sn", 1)], "x": [("I", 3)]},
}

OPV_PRESETS: dict[str, dict] = {
    "P3HT : PC61BM = 1 : 1 (20 mg/mL, CB)": {
        "materials": [("P3HT", 1), ("PC61BM", 1)], "conc": 20.0,
        "solvents": [("Chlorobenzene", 1)], "additives": [],
    },
    "PTB7-Th : PC71BM = 1 : 1.5 (25 mg/mL, CB + 3% DIO)": {
        "materials": [("PTB7-Th", 1), ("PC71BM", 1.5)], "conc": 25.0,
        "solvents": [("Chlorobenzene", 1)], "additives": [("DIO", 3)],
    },
    "PM6 : Y6 = 1 : 1.2 (16 mg/mL, CF + 0.5% 1-CN)": {
        "materials": [("PM6", 1), ("Y6", 1.2)], "conc": 16.0,
        "solvents": [("Chloroform", 1)], "additives": [("1-CN", 0.5)],
    },
    "PBDB-T : ITIC = 1 : 1 (20 mg/mL, CB + 0.5% DIO)": {
        "materials": [("PBDB-T", 1), ("ITIC", 1)], "conc": 20.0,
        "solvents": [("Chlorobenzene", 1)], "additives": [("DIO", 0.5)],
    },
}

HTL_PRESETS: dict[str, dict] = {
    "spiro-OMeTAD standard (Li-TFSI + tBP)": {
        "host": "spiro-OMeTAD", "conc": 72.3, "volume": 1.0,
        "solvents": [("Chlorobenzene", 1)],
        "dopants": [("Li-TFSI", 17.5, "uL/mL", ""), ("tBP", 28.8, "uL/mL", "")],
    },
    "spiro-OMeTAD + FK209 (Co(III) doped)": {
        "host": "spiro-OMeTAD", "conc": 72.3, "volume": 1.0,
        "solvents": [("Chlorobenzene", 1)],
        "dopants": [("Li-TFSI", 17.5, "uL/mL", ""), ("tBP", 28.8, "uL/mL", ""),
                    ("FK209", 29, "uL/mL", "")],
    },
    "PTAA 10 mg/mL (Li-TFSI + tBP)": {
        "host": "PTAA", "conc": 10.0, "volume": 1.0,
        "solvents": [("Toluene", 1)],
        "dopants": [("Li-TFSI", 7.5, "uL/mL", 170), ("tBP", 4, "uL/mL", "")],
    },
    "P3HT 15 mg/mL, undoped": {
        "host": "P3HT (HTL)", "conc": 15.0, "volume": 1.0,
        "solvents": [("Chlorobenzene", 1)], "dopants": [],
    },
}


def default_library() -> dict:
    return {
        "precursors": [dict(e) for e in chem.PRECURSORS],
        "solvents": [dict(e) for e in chem.SOLVENTS],
        "opv": [dict(e) for e in chem.OPV_MATERIALS],
        "transport": [dict(e) for e in chem.TRANSPORT_MATERIALS],
    }


def load_library() -> dict:
    lib = default_library()
    if LIB_PATH.exists():
        try:
            saved = json.loads(LIB_PATH.read_text(encoding="utf-8"))
            for key in lib:
                if isinstance(saved.get(key), list):
                    lib[key] = saved[key]
        except (json.JSONDecodeError, OSError) as exc:
            messagebox.showwarning("Library", f"Could not read library.json:\n{exc}")
    return lib


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame. Place the content in self.inner."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width)
        )
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for widget in (self.canvas, self.inner):
            widget.bind("<Enter>", self._bind_wheel)
            widget.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


class DynRows(ttk.Frame):
    """An input table whose rows can be added and removed freely.

    specs: [{"kind": "combo"|"entry", "values": [...], "width": int, "title": str}]
    """

    def __init__(self, master, specs, rows=None, add_label="+ Add row"):
        super().__init__(master)
        self.specs = specs
        self._rows: list[tuple[ttk.Frame, list[tk.Variable]]] = []

        header = ttk.Frame(self)
        header.pack(fill="x")
        for spec in specs:
            ttk.Label(header, text=spec.get("title", ""), width=spec.get("width", 12),
                      anchor="w", style="Hint.TLabel").pack(side="left", padx=(0, 4))

        self.body = ttk.Frame(self)
        self.body.pack(fill="x")
        ttk.Button(self, text=add_label, width=10,
                   command=lambda: self.add_row()).pack(anchor="w", pady=(2, 0))

        for values in (rows or [[""] * len(specs)]):
            self.add_row(values)

    def add_row(self, values=None):
        frame = ttk.Frame(self.body)
        frame.pack(fill="x", pady=1)
        vars_: list[tk.Variable] = []
        for i, spec in enumerate(self.specs):
            var = tk.StringVar(value="" if values is None else str(values[i]))
            width = spec.get("width", 12)
            if spec["kind"] == "combo":
                w = ttk.Combobox(frame, textvariable=var, values=spec.get("values", []),
                                 width=width - 2)
            else:
                w = ttk.Entry(frame, textvariable=var, width=width)
            w.pack(side="left", padx=(0, 4))
            vars_.append(var)
        ttk.Button(frame, text="✕", width=2,
                   command=lambda f=frame: self._remove(f)).pack(side="left")
        self._rows.append((frame, vars_))

    def _remove(self, frame):
        self._rows = [(f, v) for f, v in self._rows if f is not frame]
        frame.destroy()
        if not self._rows:
            self.add_row()

    def get(self) -> list[list[str]]:
        out = []
        for _, vars_ in self._rows:
            values = [v.get().strip() for v in vars_]
            if any(values):
                out.append(values)
        return out

    def get_pairs(self, name_idx=0, num_idx=1) -> list[tuple[str, float]]:
        """Convert the rows into (name, number) pairs; an empty number is 0."""
        pairs = []
        for values in self.get():
            name = values[name_idx]
            if not name:
                continue
            raw = values[num_idx]
            try:
                num = float(raw) if raw else 0.0
            except ValueError:
                raise CalcError(
                    f"Could not read the number '{raw}' in the '{name}' row."
                ) from None
            pairs.append((name, num))
        return pairs

    def set_choices(self, names, column=0):
        """Refresh the combobox choices (after the library changed)."""
        self.specs[column]["values"] = names
        combo_cols = [i for i, s in enumerate(self.specs) if s["kind"] == "combo"]
        if column not in combo_cols:
            return
        pos = combo_cols.index(column)
        for frame, _ in self._rows:
            combos = [w for w in frame.winfo_children() if isinstance(w, ttk.Combobox)]
            if pos < len(combos):
                combos[pos].configure(values=names)

    def set_rows(self, rows):
        for frame, _ in list(self._rows):
            frame.destroy()
        self._rows.clear()
        for values in (rows or [[""] * len(self.specs)]):
            self.add_row([_fmt(v) for v in values])
        if not self._rows:
            self.add_row()


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return "" if value is None else str(value)


class ResultView(ttk.Frame):
    """Result table, summary box and export buttons."""

    COLUMNS = [
        ("item", "Component", 140),
        ("formula", "Formula", 120),
        ("mw", "MW (g/mol)", 90),
        ("mmol", "Amount (mmol)", 100),
        ("mass", "Weigh (mg)", 90),
        ("vol", "Volume (µL)", 90),
        ("note", "Note", 300),
    ]

    def __init__(self, master, title="Result"):
        super().__init__(master)
        self.recipe: Recipe | None = None

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text=title, style="Head.TLabel").pack(side="left")
        ttk.Button(bar, text="Export CSV", command=self.export_csv).pack(side="right")
        ttk.Button(bar, text="Copy", command=self.copy).pack(side="right", padx=4)

        cols = [c[0] for c in self.COLUMNS]
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=13)
        for key, label, width in self.COLUMNS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width,
                             anchor="w" if key in ("item", "formula", "note") else "e")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="top", fill="both", expand=True, pady=(4, 0))
        self.tree.tag_configure("solvent", foreground="#1a5fb4")

        self.summary = tk.Text(self, height=8, wrap="word", relief="flat",
                               background="#f6f6f6", padx=8, pady=6)
        self.summary.pack(fill="x", pady=(6, 0))
        self.summary.configure(state="disabled")

    def show(self, recipe: Recipe):
        self.recipe = recipe
        self.tree.delete(*self.tree.get_children())
        for row in recipe.rows:
            self.tree.insert("", "end", values=(
                row.item,
                row.formula,
                f"{row.mw:.2f}" if row.mw else "—",
                f"{row.mmol:.4g}" if row.mmol is not None else "—",
                f"{row.mass_mg:.2f}" if row.mass_mg is not None else "—",
                f"{row.volume_uL:.1f}" if row.volume_uL is not None else "—",
                row.note,
            ), tags=("solvent",) if row.volume_uL is not None else ())

        text = "\n".join(recipe.summary)
        if recipe.warnings:
            text += "\n\n⚠ " + "\n⚠ ".join(dict.fromkeys(recipe.warnings))
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def clear(self):
        self.recipe = None
        self.tree.delete(*self.tree.get_children())
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.configure(state="disabled")

    def as_text(self) -> str:
        if not self.recipe:
            return ""
        widths = [max(len(c[1]), 12) for c in self.COLUMNS]
        lines = ["  ".join(c[1].ljust(w) for c, w in zip(self.COLUMNS, widths))]
        lines.append("-" * (sum(widths) + 2 * len(widths)))
        for iid in self.tree.get_children():
            values = self.tree.item(iid)["values"]
            lines.append("  ".join(str(v).ljust(w) for v, w in zip(values, widths)))
        return ("\n".join(lines) + "\n\n" + "\n".join(self.recipe.summary)
                + f"\n\n-- {APP_NAME} v{__version__} · {COPYRIGHT} --")

    def copy(self):
        if not self.recipe:
            return
        self.clipboard_clear()
        self.clipboard_append(self.as_text())
        messagebox.showinfo("Copy", "The result has been copied to the clipboard.")

    def export_csv(self):
        if not self.recipe:
            messagebox.showinfo("Export CSV", "Run a calculation first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="recipe.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow([c[1] for c in self.COLUMNS])
            for row in self.recipe.rows:
                writer.writerow([row.item, row.formula, row.mw, row.mmol,
                                 row.mass_mg, row.volume_uL, row.note])
            writer.writerow([])
            for line in self.recipe.summary + ["⚠ " + w for w in self.recipe.warnings]:
                writer.writerow([line])
            writer.writerow([])
            writer.writerow([f"{APP_NAME} v{__version__}", COPYRIGHT])
        messagebox.showinfo("Export CSV", f"Saved to:\n{path}")


def labeled_entry(parent, text, default="", width=10, unit=""):
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=text, width=17, anchor="w").pack(side="left")
    var = tk.StringVar(value=default)
    ttk.Entry(frame, textvariable=var, width=width).pack(side="left")
    if unit:
        ttk.Label(frame, text=unit).pack(side="left", padx=(4, 0))
    return frame, var


def section(parent, title) -> ttk.LabelFrame:
    frame = ttk.LabelFrame(parent, text=title, padding=8)
    frame.pack(fill="x", pady=(0, 8))
    return frame


def to_float(var: tk.StringVar | str, label: str, default=None) -> float:
    raw = (var.get() if isinstance(var, tk.StringVar) else var).strip()
    if not raw:
        if default is None:
            raise CalcError(f"Enter a value for {label}.")
        return default
    try:
        return float(raw)
    except ValueError:
        raise CalcError(f"Could not read '{raw}' as a number ({label}).") from None


class PerovskiteTab(ttk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master, padding=10)
        self.app = app

        left = ScrollFrame(self)
        left.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left.canvas.configure(width=440)
        panel = left.inner

        preset = section(panel, "Composition presets")
        self.preset_var = tk.StringVar()
        combo = ttk.Combobox(preset, textvariable=self.preset_var, width=47,
                             values=list(PVK_PRESETS), state="readonly")
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self.apply_preset)

        comp = section(panel, "Composition (ABX3) — ratios are normalized automatically")
        ttk.Label(comp, text="A-site cations (sum → 1)", style="Hint.TLabel").pack(anchor="w")
        self.a_rows = DynRows(comp, [
            {"kind": "combo", "values": A_CATIONS, "width": 12, "title": "Cation"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["Cs", "0.05"], ["FA", "0.79"], ["MA", "0.16"]])
        self.a_rows.pack(fill="x", pady=(2, 8))

        ttk.Label(comp, text="B-site metals (sum → 1)", style="Hint.TLabel").pack(anchor="w")
        self.b_rows = DynRows(comp, [
            {"kind": "combo", "values": B_CATIONS, "width": 12, "title": "Metal"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["Pb", "1"]])
        self.b_rows.pack(fill="x", pady=(2, 8))

        ttk.Label(comp, text="X-site halides (sum → 3)", style="Hint.TLabel").pack(anchor="w")
        self.x_rows = DynRows(comp, [
            {"kind": "combo", "values": HALIDES, "width": 12, "title": "Halide"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["I", "2.49"], ["Br", "0.51"]])
        self.x_rows.pack(fill="x", pady=(2, 0))

        cond = section(panel, "Solution conditions")
        row, self.conc_var = labeled_entry(cond, "Concentration", "1.2", unit="M (per Pb)")
        row.pack(anchor="w", pady=1)
        row, self.vol_var = labeled_entry(cond, "Total volume", "1.0", unit="mL")
        row.pack(anchor="w", pady=1)
        row, self.excess_var = labeled_entry(cond, "B-site excess", "0", unit="%")
        row.pack(anchor="w", pady=1)
        ttk.Label(cond, text="e.g. 5% PbI2 excess → enter 5",
                  style="Hint.TLabel").pack(anchor="w")

        alloc = section(panel, "Halide allocation (fraction supplied as a B-site salt)")
        self.alloc_vars = {}
        for halide, default in (("Br", "100"), ("Cl", "0"), ("I", "100")):
            row, var = labeled_entry(alloc, f"{halide} → BX2", default, width=6, unit="%")
            row.pack(anchor="w", pady=1)
            self.alloc_vars[halide] = var
        ttk.Label(alloc, text="100% → supplied as PbBr2;  0% → supplied as FABr / MABr",
                  style="Hint.TLabel", wraplength=400).pack(anchor="w")

        add = section(panel, "Additives (mol% of the formula unit)")
        self.add_rows = DynRows(add, [
            {"kind": "combo", "values": self.app.precursor_names(), "width": 18,
             "title": "Material"},
            {"kind": "entry", "width": 10, "title": "mol%"},
        ], rows=[["", ""]])
        self.add_rows.pack(fill="x")

        solv = section(panel, "Solvents (volume ratio)")
        self.solv_rows = DynRows(solv, [
            {"kind": "combo", "values": self.app.solvent_names(), "width": 18,
             "title": "Solvent"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["DMF", "4"], ["DMSO", "1"]])
        self.solv_rows.pack(fill="x")

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(4, 12))
        ttk.Button(buttons, text="Calculate", style="Accent.TButton",
                   command=self.calculate).pack(side="left")
        ttk.Button(buttons, text="Save recipe",
                   command=self.save_recipe).pack(side="left", padx=4)
        ttk.Button(buttons, text="Load", command=self.load_recipe).pack(side="left")

        self.result = ResultView(self, "Weighing table — perovskite precursor solution")
        self.result.pack(side="left", fill="both", expand=True)

    def apply_preset(self, _event=None):
        preset = PVK_PRESETS.get(self.preset_var.get())
        if not preset:
            return
        self.a_rows.set_rows([[n, v] for n, v in preset["a"]])
        self.b_rows.set_rows([[n, v] for n, v in preset["b"]])
        self.x_rows.set_rows([[n, v] for n, v in preset["x"]])
        self.add_rows.set_rows([[n, v] for n, v in preset.get("additives", [])] or None)

    def calculate(self):
        try:
            alloc = {
                h: to_float(var, f"the {h} allocation", 0.0) / 100.0
                for h, var in self.alloc_vars.items()
            }
            recipe = perovskite_recipe(
                a_sites=self.a_rows.get_pairs(),
                b_sites=self.b_rows.get_pairs(),
                x_sites=self.x_rows.get_pairs(),
                conc_M=to_float(self.conc_var, "the concentration"),
                volume_mL=to_float(self.vol_var, "the volume"),
                solvents=self.solv_rows.get_pairs(),
                additives=self.add_rows.get_pairs(),
                halide_to_b=alloc,
                library=self.app.index,
                excess_b_pct=to_float(self.excess_var, "the excess", 0.0),
            )
        except CalcError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return
        self.result.show(recipe)

    def state(self) -> dict:
        return {
            "a": self.a_rows.get(), "b": self.b_rows.get(), "x": self.x_rows.get(),
            "conc": self.conc_var.get(), "volume": self.vol_var.get(),
            "excess": self.excess_var.get(),
            "alloc": {h: v.get() for h, v in self.alloc_vars.items()},
            "additives": self.add_rows.get(), "solvents": self.solv_rows.get(),
        }

    def restore(self, data: dict):
        self.a_rows.set_rows(data.get("a"))
        self.b_rows.set_rows(data.get("b"))
        self.x_rows.set_rows(data.get("x"))
        self.conc_var.set(data.get("conc", ""))
        self.vol_var.set(data.get("volume", ""))
        self.excess_var.set(data.get("excess", "0"))
        for halide, value in (data.get("alloc") or {}).items():
            if halide in self.alloc_vars:
                self.alloc_vars[halide].set(value)
        self.add_rows.set_rows(data.get("additives"))
        self.solv_rows.set_rows(data.get("solvents"))

    def save_recipe(self):
        save_json(self.state(), "perovskite_recipe.json")

    def load_recipe(self):
        data = open_json()
        if data:
            self.restore(data)


class OPVTab(ttk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master, padding=10)
        self.app = app

        left = ScrollFrame(self)
        left.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left.canvas.configure(width=440)
        panel = left.inner

        preset = section(panel, "Blend presets")
        self.preset_var = tk.StringVar()
        combo = ttk.Combobox(preset, textvariable=self.preset_var, width=47,
                             values=list(OPV_PRESETS), state="readonly")
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self.apply_preset)

        mode = section(panel, "Concentration input mode")
        self.mode_var = tk.StringVar(value="total")
        ttk.Radiobutton(mode, text="Total concentration + weight ratio (16 mg/mL, 1:1.2)",
                        variable=self.mode_var, value="total",
                        command=self._sync_mode).pack(anchor="w")
        ttk.Radiobutton(mode, text="Individual concentration per material (mg/mL)",
                        variable=self.mode_var, value="each",
                        command=self._sync_mode).pack(anchor="w")
        row, self.conc_var = labeled_entry(mode, "Total conc.", "16", unit="mg/mL")
        row.pack(anchor="w", pady=(4, 0))
        self.conc_entry_row = row

        mats = section(panel, "Materials (donor / acceptor / other)")
        self.mat_label = ttk.Label(mats, text="Value = weight ratio", style="Hint.TLabel")
        self.mat_label.pack(anchor="w")
        self.mat_rows = DynRows(mats, [
            {"kind": "combo", "values": self.app.opv_names(), "width": 18,
             "title": "Material"},
            {"kind": "entry", "width": 10, "title": "Ratio / conc."},
        ], rows=[["PM6", "1"], ["Y6", "1.2"]])
        self.mat_rows.pack(fill="x")

        cond = section(panel, "Solution conditions")
        row, self.vol_var = labeled_entry(cond, "Total volume", "1.0", unit="mL")
        row.pack(anchor="w", pady=1)

        solv = section(panel, "Solvents (volume ratio)")
        self.solv_rows = DynRows(solv, [
            {"kind": "combo", "values": self.app.solvent_names(), "width": 18,
             "title": "Solvent"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["Chloroform", "1"]])
        self.solv_rows.pack(fill="x")

        add = section(panel, "Additives (vol% of the total volume)")
        self.add_rows = DynRows(add, [
            {"kind": "combo", "values": self.app.solvent_names(), "width": 18,
             "title": "Additive"},
            {"kind": "entry", "width": 10, "title": "vol%"},
        ], rows=[["1-CN", "0.5"]])
        self.add_rows.pack(fill="x")
        ttk.Label(add, text="The additive volume is subtracted from the solvent volume.",
                  style="Hint.TLabel", wraplength=400).pack(anchor="w")

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(4, 12))
        ttk.Button(buttons, text="Calculate", style="Accent.TButton",
                   command=self.calculate).pack(side="left")
        ttk.Button(buttons, text="Save recipe",
                   command=self.save_recipe).pack(side="left", padx=4)
        ttk.Button(buttons, text="Load", command=self.load_recipe).pack(side="left")

        self.result = ResultView(self, "Weighing table — organic solar cell blend")
        self.result.pack(side="left", fill="both", expand=True)

    def _sync_mode(self):
        total = self.mode_var.get() == "total"
        self.mat_label.configure(
            text="Value = weight ratio" if total else "Value = concentration (mg/mL)")
        for child in self.conc_entry_row.winfo_children():
            if isinstance(child, ttk.Entry):
                child.configure(state="normal" if total else "disabled")

    def apply_preset(self, _event=None):
        preset = OPV_PRESETS.get(self.preset_var.get())
        if not preset:
            return
        self.mode_var.set("total")
        self._sync_mode()
        self.conc_var.set(_fmt(preset["conc"]))
        self.mat_rows.set_rows([[n, v] for n, v in preset["materials"]])
        self.solv_rows.set_rows([[n, v] for n, v in preset["solvents"]])
        self.add_rows.set_rows([[n, v] for n, v in preset["additives"]] or None)

    def calculate(self):
        try:
            total_conc = (to_float(self.conc_var, "the total concentration")
                          if self.mode_var.get() == "total" else None)
            recipe = opv_recipe(
                materials=self.mat_rows.get_pairs(),
                volume_mL=to_float(self.vol_var, "the volume"),
                solvents=self.solv_rows.get_pairs(),
                total_conc_mgml=total_conc,
                additives=self.add_rows.get_pairs(),
                library=self.app.index,
            )
        except CalcError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return
        self.result.show(recipe)

    def state(self) -> dict:
        return {
            "mode": self.mode_var.get(), "conc": self.conc_var.get(),
            "materials": self.mat_rows.get(), "volume": self.vol_var.get(),
            "solvents": self.solv_rows.get(), "additives": self.add_rows.get(),
        }

    def restore(self, data: dict):
        self.mode_var.set(data.get("mode", "total"))
        self._sync_mode()
        self.conc_var.set(data.get("conc", ""))
        self.mat_rows.set_rows(data.get("materials"))
        self.vol_var.set(data.get("volume", ""))
        self.solv_rows.set_rows(data.get("solvents"))
        self.add_rows.set_rows(data.get("additives"))

    def save_recipe(self):
        save_json(self.state(), "opv_recipe.json")

    def load_recipe(self):
        data = open_json()
        if data:
            self.restore(data)


class TransportTab(ttk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master, padding=10)
        self.app = app

        left = ScrollFrame(self)
        left.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left.canvas.configure(width=440)
        panel = left.inner

        preset = section(panel, "Recipe presets")
        self.preset_var = tk.StringVar()
        combo = ttk.Combobox(preset, textvariable=self.preset_var, width=49,
                             values=list(HTL_PRESETS), state="readonly")
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self.apply_preset)

        host = section(panel, "Host material")
        row = ttk.Frame(host)
        row.pack(anchor="w", pady=1)
        ttk.Label(row, text="Material", width=17, anchor="w").pack(side="left")
        self.host_var = tk.StringVar(value="spiro-OMeTAD")
        self.host_combo = ttk.Combobox(row, textvariable=self.host_var, width=22,
                                       values=self.app.transport_names())
        self.host_combo.pack(side="left")
        row, self.conc_var = labeled_entry(host, "Concentration", "72.3", unit="mg/mL")
        row.pack(anchor="w", pady=1)
        row, self.vol_var = labeled_entry(host, "Solvent volume", "1.0", unit="mL")
        row.pack(anchor="w", pady=1)

        solv = section(panel, "Solvent (volume ratio)")
        self.solv_rows = DynRows(solv, [
            {"kind": "combo", "values": self.app.solvent_names(), "width": 18,
             "title": "Solvent"},
            {"kind": "entry", "width": 10, "title": "Ratio"},
        ], rows=[["Chlorobenzene", "1"]])
        self.solv_rows.pack(fill="x")

        dop = section(panel, "Dopants")
        ttk.Label(dop, wraplength=430, style="Hint.TLabel",
                  text="uL/mL = µL of stock per mL of solution. mol% is relative "
                       "to the host. Leave the stock column empty for the library "
                       "default or for neat liquids."
                  ).pack(anchor="w")
        self.dop_rows = DynRows(dop, [
            {"kind": "combo", "values": self.app.transport_names(), "width": 16,
             "title": "Dopant"},
            {"kind": "entry", "width": 8, "title": "Value"},
            {"kind": "combo", "values": list(DOPANT_UNITS), "width": 9, "title": "Unit"},
            {"kind": "entry", "width": 10, "title": "Stock mg/mL"},
        ], rows=[["Li-TFSI", "17.5", "uL/mL", ""], ["tBP", "28.8", "uL/mL", ""]])
        self.dop_rows.pack(fill="x")

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(4, 12))
        ttk.Button(buttons, text="Calculate", style="Accent.TButton",
                   command=self.calculate).pack(side="left")
        ttk.Button(buttons, text="Save recipe",
                   command=self.save_recipe).pack(side="left", padx=4)
        ttk.Button(buttons, text="Load", command=self.load_recipe).pack(side="left")

        self.result = ResultView(self, "Weighing table — charge transport layer")
        self.result.pack(side="left", fill="both", expand=True)

    def apply_preset(self, _event=None):
        preset = HTL_PRESETS.get(self.preset_var.get())
        if not preset:
            return
        self.host_var.set(preset["host"])
        self.conc_var.set(_fmt(preset["conc"]))
        self.vol_var.set(_fmt(preset.get("volume", 1.0)))
        self.solv_rows.set_rows([[n, v] for n, v in preset["solvents"]])
        self.dop_rows.set_rows([list(d) for d in preset["dopants"]] or None)

    def calculate(self):
        try:
            dopants = []
            for values in self.dop_rows.get():
                name, raw, unit, stock = (values + ["", "", "", ""])[:4]
                if not name:
                    continue
                dopants.append((
                    name,
                    to_float(raw, f"the {name} amount"),
                    unit or "uL/mL",
                    to_float(stock, f"the {name} stock concentration", 0.0) or None,
                ))
            recipe = transport_recipe(
                host=self.host_var.get().strip(),
                host_conc_mgml=to_float(self.conc_var, "the concentration"),
                volume_mL=to_float(self.vol_var, "the volume"),
                solvents=self.solv_rows.get_pairs(),
                dopants=dopants,
                library=self.app.index,
            )
        except CalcError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return
        self.result.show(recipe)

    def state(self) -> dict:
        return {
            "host": self.host_var.get(), "conc": self.conc_var.get(),
            "volume": self.vol_var.get(), "solvents": self.solv_rows.get(),
            "dopants": self.dop_rows.get(),
        }

    def restore(self, data: dict):
        self.host_var.set(data.get("host", ""))
        self.conc_var.set(data.get("conc", ""))
        self.vol_var.set(data.get("volume", ""))
        self.solv_rows.set_rows(data.get("solvents"))
        self.dop_rows.set_rows(data.get("dopants"))

    def save_recipe(self):
        save_json(self.state(), "transport_layer_recipe.json")

    def load_recipe(self):
        data = open_json()
        if data:
            self.restore(data)


class ToolsTab(ttk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master, padding=14)
        self.app = app

        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True)

        mw_box = section(left, "Molar mass calculator")
        ttk.Label(mw_box, wraplength=390, style="Hint.TLabel",
                  text="Supports abbreviations (MA, FA, PEA, OAc), nested "
                       "parentheses, fractional subscripts and hydrates "
                       "(CuSO4·5H2O).").pack(anchor="w")
        self.mw_input = tk.StringVar(value="Cs0.05FA0.79MA0.16Pb(I0.83Br0.17)3")
        entry = ttk.Entry(mw_box, textvariable=self.mw_input, width=46)
        entry.pack(anchor="w", pady=4)
        entry.bind("<Return>", lambda e: self.calc_mw())
        ttk.Button(mw_box, text="Calculate", command=self.calc_mw).pack(anchor="w")
        self.mw_out = tk.Text(mw_box, height=5, wrap="word", relief="flat",
                              background="#f6f6f6", padx=6, pady=4)
        self.mw_out.pack(fill="x", pady=(6, 0))
        self.mw_out.configure(state="disabled")

        conv = section(left, "Concentration conversion  (mg/mL ↔ mol/L)")
        row, self.conv_mw = labeled_entry(conv, "Molar mass", "461.01", unit="g/mol")
        row.pack(anchor="w", pady=1)
        row, self.conv_mgml = labeled_entry(conv, "Concentration", "", unit="mg/mL")
        row.pack(anchor="w", pady=1)
        row, self.conv_molar = labeled_entry(conv, "Concentration", "", unit="mol/L (M)")
        row.pack(anchor="w", pady=1)
        btns = ttk.Frame(conv)
        btns.pack(anchor="w", pady=4)
        ttk.Button(btns, text="mg/mL → M", command=self.to_molar).pack(side="left")
        ttk.Button(btns, text="M → mg/mL", command=self.to_mgml).pack(side="left", padx=4)
        ttk.Button(btns, text="Get MW from library",
                   command=self.pick_mw).pack(side="left")
        self.conv_pick = tk.StringVar()
        ttk.Combobox(conv, textvariable=self.conv_pick, width=24,
                     values=self.app.all_names()).pack(anchor="w")

        dil = section(right, "Dilution  C1·V1 = C2·V2")
        ttk.Label(dil, text="Leave exactly one field empty — that is what gets solved.",
                  style="Hint.TLabel", wraplength=390).pack(anchor="w")
        row, self.c1 = labeled_entry(dil, "Stock conc. C1", "20", unit="mg/mL or M")
        row.pack(anchor="w", pady=1)
        row, self.v1 = labeled_entry(dil, "Stock volume V1", "", unit="mL")
        row.pack(anchor="w", pady=1)
        row, self.c2 = labeled_entry(dil, "Target conc. C2", "10", unit="mg/mL or M")
        row.pack(anchor="w", pady=1)
        row, self.v2 = labeled_entry(dil, "Target volume V2", "1", unit="mL")
        row.pack(anchor="w", pady=1)
        ttk.Button(dil, text="Calculate", command=self.calc_dilution).pack(anchor="w", pady=4)
        self.dil_out = tk.Text(dil, height=5, wrap="word", relief="flat",
                               background="#f6f6f6", padx=6, pady=4)
        self.dil_out.pack(fill="x")
        self.dil_out.configure(state="disabled")

        stock = section(right, "Prepare a solution from a stock")
        row, self.s_conc = labeled_entry(stock, "Stock conc.", "1.5", unit="M or mg/mL")
        row.pack(anchor="w", pady=1)
        row, self.t_conc = labeled_entry(stock, "Target conc.", "1.2", unit="M or mg/mL")
        row.pack(anchor="w", pady=1)
        row, self.t_vol = labeled_entry(stock, "Target volume", "1.0", unit="mL")
        row.pack(anchor="w", pady=1)
        ttk.Button(stock, text="Calculate", command=self.calc_stock).pack(anchor="w", pady=4)
        self.stock_out = tk.Text(stock, height=5, wrap="word", relief="flat",
                                 background="#f6f6f6", padx=6, pady=4)
        self.stock_out.pack(fill="x")
        self.stock_out.configure(state="disabled")

    @staticmethod
    def _write(widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def calc_mw(self):
        formula = self.mw_input.get().strip()
        try:
            counts = chem.parse_formula(formula)
            mw = chem.molar_mass(formula)
        except (chem.FormulaError, KeyError) as exc:
            self._write(self.mw_out, f"Error: {exc}")
            return
        parts = ", ".join(
            f"{el} {n:g} × {chem.ATOMIC_MASS[el]:.3f} = {n * chem.ATOMIC_MASS[el]:.3f}"
            for el, n in sorted(counts.items())
        )
        self._write(self.mw_out, f"MW = {mw:.3f} g/mol\n\n{parts}")

    def _mw(self) -> float:
        return to_float(self.conv_mw, "the molar mass")

    def to_molar(self):
        try:
            value = mgml_to_molar(to_float(self.conv_mgml, "the mg/mL concentration"),
                                  self._mw())
        except CalcError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return
        self.conv_molar.set(f"{value:.6g}")

    def to_mgml(self):
        try:
            value = molar_to_mgml(to_float(self.conv_molar, "the molarity"), self._mw())
        except CalcError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return
        self.conv_mgml.set(f"{value:.6g}")

    def pick_mw(self):
        name = self.conv_pick.get().strip()
        if not name:
            return
        mw = chem.lookup_mw(name, self.app.index)
        if mw is None:
            messagebox.showinfo("Molar mass", f"No molar mass is known for '{name}'.")
            return
        self.conv_mw.set(f"{mw:.4g}")

    def calc_dilution(self):
        try:
            c1 = to_float(self.c1, "C1")
            c2 = to_float(self.c2, "C2")
            v1 = self.v1.get().strip()
            v2 = self.v2.get().strip()
            v1_val = float(v1) if v1 else None
            v2_val = float(v2) if v2 else None
            v1_out, v2_out = dilution(c1, v1_val, c2, v2_val)
        except (CalcError, ValueError) as exc:
            self._write(self.dil_out, f"Error: {exc}")
            return
        self.v1.set(f"{v1_out:.6g}")
        self.v2.set(f"{v2_out:.6g}")
        self._write(self.dil_out,
                    f"Stock  {v1_out:.4g} mL ({v1_out * 1000:.1f} µL)\n"
                    f"+ solvent  {v2_out - v1_out:.4g} mL "
                    f"({(v2_out - v1_out) * 1000:.1f} µL)\n"
                    f"= {v2_out:.4g} mL total at {c2:g}\n"
                    f"Dilution factor {c1 / c2:.3g}×")

    def calc_stock(self):
        try:
            v_stock, v_solvent = from_stock(
                to_float(self.s_conc, "the stock concentration"),
                to_float(self.t_conc, "the target concentration"),
                to_float(self.t_vol, "the target volume"),
            )
        except CalcError as exc:
            self._write(self.stock_out, f"Error: {exc}")
            return
        self._write(self.stock_out,
                    f"Stock  {v_stock:.4g} mL ({v_stock * 1000:.1f} µL)\n"
                    f"Solvent  {v_solvent:.4g} mL ({v_solvent * 1000:.1f} µL)\n"
                    f"Total  {v_stock + v_solvent:.4g} mL")


class LibraryTab(ttk.Frame):
    KINDS = {"precursors": "Precursors", "solvents": "Solvents",
             "opv": "OPV materials", "transport": "Transport layer"}

    def __init__(self, master, app: "App"):
        super().__init__(master, padding=12)
        self.app = app

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Category", width=9).pack(side="left")
        self.kind_var = tk.StringVar(value="precursors")
        combo = ttk.Combobox(top, width=20, state="readonly",
                             values=list(self.KINDS.values()))
        combo.set(self.KINDS["precursors"])
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self.select_kind(combo.get()))
        ttk.Button(top, text="Save library.json", command=self.save).pack(side="right")
        ttk.Button(top, text="Restore defaults",
                   command=self.reset).pack(side="right", padx=6)

        cols = ("name", "formula", "mw", "density", "extra")
        heads = ("Name", "Formula", "MW (g/mol)", "Density (g/mL)", "Note")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=17)
        for key, label, width in zip(cols, heads, (170, 190, 110, 120, 200)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.Frame(self)
        form.pack(fill="x")
        self.f_name = tk.StringVar()
        self.f_formula = tk.StringVar()
        self.f_density = tk.StringVar()
        self.f_note = tk.StringVar()
        for label, var, width in (("Name", self.f_name, 16),
                                  ("Formula", self.f_formula, 20),
                                  ("Density (g/mL)", self.f_density, 8),
                                  ("Note", self.f_note, 20)):
            ttk.Label(form, text=label).pack(side="left", padx=(0, 3))
            ttk.Entry(form, textvariable=var, width=width).pack(side="left", padx=(0, 10))
        ttk.Button(form, text="Add / Update", command=self.upsert).pack(side="left")
        ttk.Button(form, text="Delete", command=self.delete).pack(side="left", padx=4)

        ttk.Label(self, style="Hint.TLabel", wraplength=900,
                  text="The molar mass is derived from the formula. Materials added "
                       "here appear immediately in the other tabs; press "
                       "'Save library.json' to keep them for the next run."
                  ).pack(anchor="w", pady=(8, 0))
        self.refresh()

    def select_kind(self, label: str):
        for key, text in self.KINDS.items():
            if text == label:
                self.kind_var.set(key)
        self.refresh()

    def entries(self) -> list[dict]:
        return self.app.library[self.kind_var.get()]

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for entry in self.entries():
            mw = entry.get("mw") or chem.safe_mw(entry.get("formula"))
            self.tree.insert("", "end", values=(
                entry.get("name", ""),
                entry.get("formula") or "",
                f"{mw:.2f}" if mw else "—",
                _fmt(entry.get("density")),
                entry.get("note") or entry.get("category") or entry.get("role") or "",
            ))
        self.app.refresh_choices()

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        name, formula, _mw, density, note = self.tree.item(selection[0])["values"]
        self.f_name.set(name)
        self.f_formula.set(formula)
        self.f_density.set(density)
        self.f_note.set(note)

    def upsert(self):
        name = self.f_name.get().strip()
        if not name:
            messagebox.showinfo("Library", "Enter a name.")
            return
        formula = self.f_formula.get().strip()
        if formula and chem.safe_mw(formula) is None:
            messagebox.showwarning("Library", f"Could not parse the formula '{formula}'.")
        entry = {"name": name, "formula": formula or None,
                 "note": self.f_note.get().strip()}
        density = self.f_density.get().strip()
        if density:
            try:
                entry["density"] = float(density)
            except ValueError:
                messagebox.showerror("Library", "The density must be a number.")
                return
        entries = self.entries()
        for i, existing in enumerate(entries):
            if existing.get("name") == name:
                entries[i] = {**existing, **entry}
                break
        else:
            entries.append(entry)
        self.refresh()

    def delete(self):
        name = self.f_name.get().strip()
        entries = self.entries()
        remaining = [e for e in entries if e.get("name") != name]
        if len(remaining) == len(entries):
            return
        self.app.library[self.kind_var.get()] = remaining
        self.refresh()

    def save(self):
        try:
            LIB_PATH.write_text(
                json.dumps(self.app.library, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        messagebox.showinfo("Library", f"Saved to:\n{LIB_PATH}")

    def reset(self):
        if messagebox.askyesno("Restore defaults",
                               "Reset the library to the built-in defaults?"):
            self.app.library = default_library()
            self.refresh()


def save_json(data: dict, initial: str):
    path = filedialog.asksaveasfilename(defaultextension=".json",
                                        filetypes=[("JSON", "*.json")],
                                        initialfile=initial)
    if not path:
        return
    try:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except OSError as exc:
        messagebox.showerror("Save failed", str(exc))
        return
    messagebox.showinfo("Save recipe", f"Saved to:\n{path}")


def open_json() -> dict | None:
    path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        messagebox.showerror("Load failed", str(exc))
        return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{__version__} — perovskite / organic solar cells "
                   f"|  {COPYRIGHT}")
        self.geometry("1420x850")
        self.minsize(1120, 700)

        self.library = load_library()
        self.index: dict[str, dict] = {}
        self._reindex()

        style = ttk.Style(self)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        style.configure("Head.TLabel", font=("", 13, "bold"))
        style.configure("Hint.TLabel", foreground="#666")
        try:
            style.configure("Accent.TButton", font=("", 12, "bold"))
        except tk.TclError:
            pass

        header = ttk.Frame(self, padding=(12, 8, 12, 0))
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Head.TLabel").pack(side="left")
        ttk.Label(header, style="Hint.TLabel",
                  text="  perovskite precursors · organic blends · "
                       "concentration and dilution tools").pack(side="left")
        ttk.Button(header, text="About", width=6,
                   command=self.show_about).pack(side="right", padx=(8, 0))
        ttk.Label(header, text=f"{COPYRIGHT}  ·  v{__version__}",
                  style="Hint.TLabel").pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=8)
        self.pvk = PerovskiteTab(self.nb, self)
        self.opv = OPVTab(self.nb, self)
        self.htl = TransportTab(self.nb, self)
        self.tools = ToolsTab(self.nb, self)
        self.lib_tab = LibraryTab(self.nb, self)
        self.nb.add(self.pvk, text="  Perovskite  ")
        self.nb.add(self.opv, text="  Organic solar cell  ")
        self.nb.add(self.htl, text="  Transport layer  ")
        self.nb.add(self.tools, text="  Convert · Dilute  ")
        self.nb.add(self.lib_tab, text="  Material library  ")

        self.status = ttk.Label(
            self, style="Hint.TLabel", padding=(12, 0, 12, 8),
            text="Fill in the inputs and press [Calculate]. "
                 "Solvent volumes ignore the volume of the solutes.")
        self.status.pack(fill="x")

    def show_about(self):
        messagebox.showinfo(
            "About",
            f"{APP_NAME}  v{__version__}\n"
            "Precursor weighing and solvent mixing for solution-processed\n"
            "perovskite and organic solar cells.\n\n"
            f"Author : {__author__}\n"
            f"{__copyright__}\n"
            f"License : {__license__}\n\n"
            f"{REPO_URL}",
        )

    def _reindex(self):
        self.index = {}
        for key in ("precursors", "solvents", "opv", "transport"):
            for entry in self.library.get(key, []):
                self.index[entry["name"]] = entry

    def precursor_names(self) -> list[str]:
        return sorted(e["name"] for e in self.library["precursors"])

    def solvent_names(self) -> list[str]:
        return sorted(e["name"] for e in self.library["solvents"])

    def opv_names(self) -> list[str]:
        return sorted(e["name"] for e in self.library["opv"])

    def transport_names(self) -> list[str]:
        return sorted(e["name"] for e in self.library["transport"])

    def all_names(self) -> list[str]:
        return sorted(self.index)

    def refresh_choices(self):
        """Update the comboboxes in every tab after a library change."""
        self._reindex()
        if not hasattr(self, "pvk"):
            return
        for rows, names in (
            (self.pvk.add_rows, self.precursor_names()),
            (self.pvk.solv_rows, self.solvent_names()),
            (self.opv.mat_rows, self.opv_names()),
            (self.opv.solv_rows, self.solvent_names()),
            (self.opv.add_rows, self.solvent_names()),
            (self.htl.solv_rows, self.solvent_names()),
            (self.htl.dop_rows, self.transport_names()),
        ):
            rows.set_choices(names)
        self.htl.host_combo.configure(values=self.transport_names())


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
