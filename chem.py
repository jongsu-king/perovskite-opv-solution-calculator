# Copyright (c) 2026 Jongsu Lim
# SPDX-License-Identifier: MIT
"""Formula parsing, molar mass calculation, and the built-in material library.

Used by the solution preparation calculator for perovskite and organic solar
cells. No third-party dependencies (standard library only).
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Standard atomic weights (IUPAC), g/mol
# --------------------------------------------------------------------------
ATOMIC_MASS: dict[str, float] = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.95, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938,
    "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Tc": 98.0, "Ru": 101.07, "Rh": 102.91,
    "Pd": 106.42, "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71,
    "Sb": 121.76, "Te": 127.60, "I": 126.904, "Xe": 131.29, "Cs": 132.905,
    "Ba": 137.33, "La": 138.91, "Ce": 140.12, "Eu": 151.96, "Yb": 173.05,
    "Hf": 178.49, "Ta": 180.95, "W": 183.84, "Re": 186.21, "Os": 190.23,
    "Ir": 192.22, "Pt": 195.08, "Au": 196.97, "Hg": 200.59, "Tl": 204.38,
    "Pb": 207.2, "Bi": 208.98,
}

# --------------------------------------------------------------------------
# Abbreviations for organic cations and ligands (expanded to real formulas)
# --------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    "MA": "CH6N",        # methylammonium, CH3NH3+
    "FA": "CH5N2",       # formamidinium, CH(NH2)2+
    "GA": "CH6N3",       # guanidinium, C(NH2)3+
    "EA": "C2H8N",       # ethylammonium
    "PA": "C3H10N",      # n-propylammonium
    "BA": "C4H12N",      # n-butylammonium
    "OA": "C8H20N",      # n-octylammonium
    "PEA": "C8H12N",     # phenethylammonium
    "PMA": "C7H10N",     # benzylammonium (phenylmethylammonium)
    "TBA": "C16H36N",    # tetrabutylammonium
    "OAc": "C2H3O2",     # acetate
    "Ac": "C2H3O2",      # acetate (conventional shorthand)
    "Me": "CH3",
    "Et": "C2H5",
    "Ph": "C6H5",
}

_ALIAS_KEYS = sorted(ALIASES, key=len, reverse=True)
_HYDRATE_SPLIT = re.compile(r"[·•*]|\.(?![0-9])")
_LEADING_NUM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?=[A-Za-z(\[])")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class FormulaError(ValueError):
    """Raised when a chemical formula cannot be parsed."""


def _merge(dst: dict[str, float], src: dict[str, float], factor: float = 1.0) -> None:
    for el, n in src.items():
        dst[el] = dst.get(el, 0.0) + n * factor


def _parse_group(text: str) -> dict[str, float]:
    """Parse one formula fragment (parentheses included) into element counts."""
    stack: list[dict[str, float]] = [{}]
    i, n = 0, len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch in "([{":
            stack.append({})
            i += 1
            continue

        if ch in ")]}":
            if len(stack) == 1:
                raise FormulaError(f"Unbalanced parentheses: {text!r}")
            group = stack.pop()
            i += 1
            m = _NUMBER.match(text, i)
            mult = float(m.group()) if m else 1.0
            if m:
                i = m.end()
            _merge(stack[-1], group, mult)
            continue

        # Check abbreviations (MA, FA, PEA, OAc ...) before element symbols
        token = next((a for a in _ALIAS_KEYS if text.startswith(a, i)), None)
        if token is not None:
            unit = _parse_group(ALIASES[token])
            i += len(token)
        else:
            m = re.match(r"[A-Z][a-z]?", text[i:])
            if not m:
                raise FormulaError(f"Unexpected character {text[i]!r} in {text!r}")
            sym = m.group()
            if sym not in ATOMIC_MASS:
                sym = sym[0]
                if sym not in ATOMIC_MASS:
                    raise FormulaError(f"Unknown element symbol {m.group()!r} in {text!r}")
            unit = {sym: 1.0}
            i += len(sym)

        m = _NUMBER.match(text, i)
        cnt = float(m.group()) if m else 1.0
        if m:
            i = m.end()
        _merge(stack[-1], unit, cnt)

    if len(stack) != 1:
        raise FormulaError(f"Unclosed parenthesis: {text!r}")
    return stack[0]


def parse_formula(formula: str) -> dict[str, float]:
    """Convert a formula string into {element: count}.

    Supports nested parentheses/brackets, fractional subscripts (Cs0.05),
    hydrate notation (CuSO4·5H2O) and organic cation abbreviations
    (MA, FA, PEA, OAc ...).
    """
    if not formula or not formula.strip():
        raise FormulaError("The formula is empty.")

    total: dict[str, float] = {}
    for part in _HYDRATE_SPLIT.split(formula.strip()):
        part = part.strip()
        if not part:
            continue
        mult = 1.0
        m = _LEADING_NUM.match(part)
        if m:
            mult = float(m.group(1))
            part = part[m.end():]
        _merge(total, _parse_group(part), mult)
    if not total:
        raise FormulaError(f"Nothing to parse in {formula!r}")
    return total


def molar_mass(formula: str) -> float:
    """Molar mass of a formula, in g/mol."""
    return sum(ATOMIC_MASS[el] * n for el, n in parse_formula(formula).items())


# --------------------------------------------------------------------------
# Built-in library
# --------------------------------------------------------------------------
# category: A (A-site salt) / B (B-site salt) / additive
PRECURSORS: list[dict] = [
    # --- B-site (metal halides) ---
    {"name": "PbI2",  "formula": "PbI2",  "category": "B"},
    {"name": "PbBr2", "formula": "PbBr2", "category": "B"},
    {"name": "PbCl2", "formula": "PbCl2", "category": "B"},
    {"name": "SnI2",  "formula": "SnI2",  "category": "B"},
    {"name": "SnBr2", "formula": "SnBr2", "category": "B"},
    {"name": "SnCl2", "formula": "SnCl2", "category": "B"},
    {"name": "GeI2",  "formula": "GeI2",  "category": "B"},
    # --- A-site (organic / inorganic halide salts) ---
    {"name": "MAI",   "formula": "MAI",   "category": "A"},
    {"name": "MABr",  "formula": "MABr",  "category": "A"},
    {"name": "MACl",  "formula": "MACl",  "category": "A"},
    {"name": "FAI",   "formula": "FAI",   "category": "A"},
    {"name": "FABr",  "formula": "FABr",  "category": "A"},
    {"name": "FACl",  "formula": "FACl",  "category": "A"},
    {"name": "CsI",   "formula": "CsI",   "category": "A"},
    {"name": "CsBr",  "formula": "CsBr",  "category": "A"},
    {"name": "CsCl",  "formula": "CsCl",  "category": "A"},
    {"name": "RbI",   "formula": "RbI",   "category": "A"},
    {"name": "RbCl",  "formula": "RbCl",  "category": "A"},
    {"name": "GAI",   "formula": "GAI",   "category": "A"},
    {"name": "GABr",  "formula": "GABr",  "category": "A"},
    {"name": "PEAI",  "formula": "PEAI",  "category": "A"},
    {"name": "PEABr", "formula": "PEABr", "category": "A"},
    {"name": "BAI",   "formula": "BAI",   "category": "A"},
    {"name": "OAI",   "formula": "OAI",   "category": "A"},
    # --- Additives ---
    {"name": "Pb(SCN)2",   "formula": "Pb(SCN)2",   "category": "additive"},
    {"name": "MASCN",      "formula": "MASCN",      "category": "additive"},
    {"name": "KI",         "formula": "KI",         "category": "additive"},
    {"name": "NH4Cl",      "formula": "NH4Cl",      "category": "additive"},
    {"name": "NH4SCN",     "formula": "NH4SCN",     "category": "additive"},
    {"name": "PbAc2·3H2O", "formula": "Pb(OAc)2·3H2O", "category": "additive"},
    {"name": "CsAc",       "formula": "CsOAc",      "category": "additive"},
    {"name": "MDACl2",     "formula": "C2H10N2Cl2", "category": "additive"},
]

# density: g/mL (literature values near 25 °C), bp: °C
SOLVENTS: list[dict] = [
    {"name": "DMF",           "formula": "C3H7NO",    "density": 0.944, "bp": 153},
    {"name": "DMSO",          "formula": "C2H6OS",    "density": 1.100, "bp": 189},
    {"name": "GBL",           "formula": "C4H6O2",    "density": 1.129, "bp": 204},
    {"name": "NMP",           "formula": "C5H9NO",    "density": 1.028, "bp": 202},
    {"name": "DMAc",          "formula": "C4H9NO",    "density": 0.937, "bp": 165},
    {"name": "2-ME",          "formula": "C3H8O2",    "density": 0.965, "bp": 124},
    {"name": "ACN",           "formula": "C2H3N",     "density": 0.786, "bp": 82},
    {"name": "IPA",           "formula": "C3H8O",     "density": 0.786, "bp": 82},
    {"name": "Chlorobenzene", "formula": "C6H5Cl",    "density": 1.106, "bp": 131},
    {"name": "o-DCB",         "formula": "C6H4Cl2",   "density": 1.306, "bp": 180},
    {"name": "Chloroform",    "formula": "CHCl3",     "density": 1.489, "bp": 61},
    {"name": "Toluene",       "formula": "C7H8",      "density": 0.867, "bp": 111},
    {"name": "o-Xylene",      "formula": "C8H10",     "density": 0.880, "bp": 144},
    {"name": "Anisole",       "formula": "C7H8O",     "density": 0.995, "bp": 154},
    {"name": "THF",           "formula": "C4H8O",     "density": 0.889, "bp": 66},
    {"name": "CS2",           "formula": "CS2",       "density": 1.266, "bp": 46},
    {"name": "DIO",           "formula": "C8H16I2",   "density": 1.837, "bp": 168},
    {"name": "1-CN",          "formula": "C10H7Cl",   "density": 1.194, "bp": 259},
    {"name": "DPE",           "formula": "C12H10O",   "density": 1.073, "bp": 258},
]

# Organic photovoltaic materials. The blend calculation is mass-based, so the
# molar mass is optional (leave the formula as None when it is not meaningful).
OPV_MATERIALS: list[dict] = [
    {"name": "P3HT",     "role": "donor",    "formula": "C10H14S",
     "note": "MW of the repeat unit"},
    {"name": "PM6",      "role": "donor",    "formula": None},
    {"name": "PM7",      "role": "donor",    "formula": None},
    {"name": "PTB7-Th",  "role": "donor",    "formula": None},
    {"name": "PBDB-T",   "role": "donor",    "formula": None},
    {"name": "D18",      "role": "donor",    "formula": None},
    {"name": "PTQ10",    "role": "donor",    "formula": None},
    {"name": "PC61BM",   "role": "acceptor", "formula": "C72H14O2"},
    {"name": "PC71BM",   "role": "acceptor", "formula": "C82H14O2"},
    {"name": "ICBA",     "role": "acceptor", "formula": "C78H14"},
    {"name": "Y6",       "role": "acceptor", "formula": None},
    {"name": "L8-BO",    "role": "acceptor", "formula": None},
    {"name": "BTP-eC9",  "role": "acceptor", "formula": None},
    {"name": "ITIC",     "role": "acceptor", "formula": None},
    {"name": "IT-4F",    "role": "acceptor", "formula": None},
    {"name": "PDINN",    "role": "other",    "formula": None},
]


def safe_mw(formula: str | None) -> float | None:
    """Molar mass that returns None instead of raising."""
    if not formula:
        return None
    try:
        return molar_mass(formula)
    except (FormulaError, KeyError):
        return None


def build_index(entries: list[dict]) -> dict[str, dict]:
    return {e["name"]: e for e in entries}


def lookup_mw(name: str, library: dict[str, dict] | None = None) -> float | None:
    """Look up a molar mass by name, falling back to parsing the name itself.

    Materials that are registered in the library but have no formula or MW
    (polymers and non-fullerene acceptors such as PM6 or Y6) return None, so
    that their names are never mistaken for chemical formulas.
    """
    if library and name in library:
        entry = library[name]
        if entry.get("mw"):
            return float(entry["mw"])
        return safe_mw(entry.get("formula"))
    return safe_mw(name)
