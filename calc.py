# Copyright (c) 2026 Jongsu Lim
# SPDX-License-Identifier: MIT
"""Solution preparation math, kept free of any GUI dependency.

- perovskite_recipe : ABX3 composition  -> precursor masses + solvent volumes
- opv_recipe        : donor:acceptor blend -> material masses + solvent volumes
- helpers           : unit conversion, dilution, stock solution mixing
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chem import lookup_mw

EPS = 1e-9


@dataclass
class Row:
    """One line of the result table."""
    item: str
    formula: str = ""
    mw: float | None = None
    mmol: float | None = None
    mass_mg: float | None = None
    volume_uL: float | None = None
    note: str = ""


@dataclass
class Recipe:
    rows: list[Row] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CalcError(ValueError):
    """Raised when the user input is not physically consistent."""


def _normalize(items: list[tuple[str, float]], total: float, what: str) -> list[tuple[str, float]]:
    """Scale (name, value) pairs so that the values sum to `total`."""
    items = [(n, v) for n, v in items if n and v > EPS]
    if not items:
        raise CalcError(f"Enter at least one {what} entry.")
    s = sum(v for _, v in items)
    return [(n, v / s * total) for n, v in items]


def _salt_name(cation: str, halide: str, b_site: bool) -> str:
    return f"{cation}{halide}2" if b_site else f"{cation}{halide}"


def perovskite_recipe(
    a_sites: list[tuple[str, float]],
    b_sites: list[tuple[str, float]],
    x_sites: list[tuple[str, float]],
    conc_M: float,
    volume_mL: float,
    solvents: list[tuple[str, float]],
    additives: list[tuple[str, float]] | None = None,
    halide_to_b: dict[str, float] | None = None,
    library: dict[str, dict] | None = None,
    excess_b_pct: float = 0.0,
) -> Recipe:
    """Turn an ABX3 composition into precursor weighing masses.

    a_sites/b_sites : [(cation, relative ratio)] - each normalized to 1
    x_sites         : [(halide, relative ratio)] - normalized to 3
    conc_M          : molarity of the formula unit (= B-site metal), mol/L
    halide_to_b     : {halide: 0..1} fraction supplied as a B-site salt
                      (defaults: Br and I to the maximum, Cl to 0)
    excess_b_pct    : excess of the B-site halide in % (e.g. 5% PbI2 excess)
    """
    if conc_M <= 0:
        raise CalcError("Concentration must be greater than 0.")
    if volume_mL <= 0:
        raise CalcError("Volume must be greater than 0.")

    a_sites = _normalize(a_sites, 1.0, "A-site")
    b_sites = _normalize(b_sites, 1.0, "B-site")
    x_sites = _normalize(x_sites, 3.0, "halide (X-site)")

    halide_to_b = dict(halide_to_b or {})
    order = ["Cl", "Br", "I"]
    x_map = {n: v for n, v in x_sites}
    for h in x_map:
        halide_to_b.setdefault(h, 0.0 if h == "Cl" else 1.0)

    b_budget, a_budget = 2.0, 1.0
    to_b: dict[str, float] = {}
    to_a: dict[str, float] = {}
    warnings: list[str] = []

    for h in order + [k for k in x_map if k not in order]:
        if h not in x_map:
            continue
        want = x_map[h] * max(0.0, min(1.0, halide_to_b[h]))
        nb = min(want, b_budget)
        na = x_map[h] - nb
        if na > a_budget + EPS:
            shift = min(na - a_budget, b_budget - nb)
            nb, na = nb + shift, na - shift
            warnings.append(
                f"The {h} allocation was adjusted automatically "
                f"(the A-site salt limit was exceeded)."
            )
        if na > a_budget + EPS or nb > b_budget + EPS:
            raise CalcError(
                f"{h} cannot be allocated. Check the halide composition "
                f"or the allocation percentages."
            )
        to_b[h], to_a[h] = nb, na
        b_budget -= nb
        a_budget -= na

    if abs(b_budget) > 1e-6 or abs(a_budget) > 1e-6:
        raise CalcError("Check the composition: the halides must add up to 3.")

    total_mol = conc_M * volume_mL / 1000.0
    rows: list[Row] = []
    warn = list(warnings)

    def add_salt(cation: str, halide: str, per_fu: float, b_site: bool) -> None:
        if per_fu <= EPS:
            return
        name = _salt_name(cation, halide, b_site)
        mw = lookup_mw(name, library)
        mol = per_fu * total_mol
        if b_site and excess_b_pct:
            mol *= 1.0 + excess_b_pct / 100.0
        if mw is None:
            warn.append(f"No molar mass found for {name} (add it to the library).")
            rows.append(Row(name, name, None, mol * 1000, None, note="MW unknown"))
            return
        rows.append(Row(
            item=name, formula=name, mw=mw, mmol=mol * 1000,
            mass_mg=mol * mw * 1000,
            note=f"{per_fu:.4g} eq"
                 + (f", +{excess_b_pct:g}% excess" if b_site and excess_b_pct else ""),
        ))

    for cation, frac in b_sites:
        for h, amount in to_b.items():
            add_salt(cation, h, frac * amount / 2.0, True)
    for cation, frac in a_sites:
        for h, amount in to_a.items():
            add_salt(cation, h, frac * amount, False)

    for name, pct in (additives or []):
        if not name or abs(pct) < EPS:
            continue
        mw = lookup_mw(name, library)
        mol = total_mol * pct / 100.0
        rows.append(Row(
            item=name, formula=name, mw=mw, mmol=mol * 1000,
            mass_mg=(mol * mw * 1000) if mw else None,
            note=f"additive {pct:g} mol%" + ("" if mw else " / MW unknown"),
        ))
        if mw is None:
            warn.append(f"No molar mass found for {name}.")

    rows += _solvent_rows(solvents, volume_mL, library)

    solid = sum(r.mass_mg for r in rows if r.mass_mg and r.volume_uL is None)
    tiny = [r.item for r in rows if r.mass_mg is not None and 0 < r.mass_mg < 2.0]
    if tiny:
        warn.append(
            "Below 2 mg to weigh: " + ", ".join(tiny)
            + " - preparing a stock solution and pipetting it is more accurate."
        )

    formula_txt = _pretty_formula(a_sites, b_sites, x_sites)
    summary = [
        f"Target composition : {formula_txt}",
        f"Concentration / volume : {conc_M:g} M x {volume_mL:g} mL "
        f"(= {total_mol * 1000:.4g} mmol of formula units)",
        f"Total solid mass : {solid:.2f} mg",
        "Solvent volumes ignore the volume of the solutes (common practice).",
    ]
    return Recipe(rows, summary, warn)


def _pretty_formula(a_sites, b_sites, x_sites) -> str:
    def part(items):
        return "".join(
            n if abs(v - 1.0) < 1e-6 else f"{n}{round(v, 4):g}" for n, v in items
        )
    return part(a_sites) + part(b_sites) + part(x_sites)


def _solvent_rows(solvents, volume_mL, library, available_mL=None) -> list[Row]:
    """Split the available volume among the solvents by volume ratio."""
    solvents = [(n, v) for n, v in solvents if n and v > EPS]
    if not solvents:
        raise CalcError("Enter at least one solvent.")
    vol = volume_mL if available_mL is None else available_mL
    if vol < -EPS:
        raise CalcError("The additive volume exceeds the total volume.")
    total_ratio = sum(v for _, v in solvents)
    rows = []
    for name, ratio in solvents:
        v_mL = vol * ratio / total_ratio
        entry = (library or {}).get(name, {})
        density = entry.get("density")
        rows.append(Row(
            item=name,
            formula=entry.get("formula") or "",
            mw=lookup_mw(name, library),
            mass_mg=(v_mL * density * 1000) if density else None,
            volume_uL=v_mL * 1000,
            note=f"solvent · ratio {ratio:g} ({ratio / total_ratio * 100:.1f} vol%)",
        ))
    return rows


def opv_recipe(
    materials: list[tuple[str, float]],
    volume_mL: float,
    solvents: list[tuple[str, float]],
    total_conc_mgml: float | None = None,
    additives: list[tuple[str, float]] | None = None,
    library: dict[str, dict] | None = None,
) -> Recipe:
    """Calculate a donor:acceptor blend solution.

    materials       : [(name, value)] - with total_conc_mgml the value is a
                      weight ratio, otherwise an individual concentration (mg/mL)
    additives       : [(name, vol%)] - v/v % of the total volume, subtracted
                      from the solvent volume
    """
    if volume_mL <= 0:
        raise CalcError("Volume must be greater than 0.")
    mats = [(n, v) for n, v in materials if n and v > EPS]
    if not mats:
        raise CalcError("Enter at least one material.")

    rows: list[Row] = []
    warn: list[str] = []

    if total_conc_mgml is not None:
        if total_conc_mgml <= 0:
            raise CalcError("The total concentration must be greater than 0.")
        ratio_sum = sum(v for _, v in mats)
        concs = [(n, total_conc_mgml * v / ratio_sum) for n, v in mats]
    else:
        concs = mats
    ratio_txt = " : ".join(f"{v:g}" for _, v in mats)

    for (name, conc), (_, raw) in zip(concs, mats):
        mass_mg = conc * volume_mL
        mw = lookup_mw(name, library)
        rows.append(Row(
            item=name, formula=(library or {}).get(name, {}).get("formula") or "",
            mw=mw,
            mmol=(mass_mg / mw) if mw else None,
            mass_mg=mass_mg,
            note=f"{conc:.4g} mg/mL"
                 + (f" · ratio {raw:g}" if total_conc_mgml is not None else ""),
        ))

    add_vol_mL = 0.0
    add_rows: list[Row] = []
    for name, pct in (additives or []):
        if not name or pct <= EPS:
            continue
        v_mL = volume_mL * pct / 100.0
        add_vol_mL += v_mL
        entry = (library or {}).get(name, {})
        density = entry.get("density")
        add_rows.append(Row(
            item=name, formula=entry.get("formula") or "",
            mw=lookup_mw(name, library),
            mass_mg=(v_mL * density * 1000) if density else None,
            volume_uL=v_mL * 1000,
            note=f"additive {pct:g} vol%" + ("" if density else " / density unknown"),
        ))
        if not density:
            warn.append(f"No density for {name}, so its mass could not be calculated.")

    rows += _solvent_rows(solvents, volume_mL, library, available_mL=volume_mL - add_vol_mL)
    rows += add_rows

    total_solid = sum(r.mass_mg for r in rows if r.volume_uL is None and r.mass_mg)
    tiny = [r.item for r in rows if r.volume_uL is None and r.mass_mg and r.mass_mg < 1.0]
    if tiny:
        warn.append("Below 1 mg to weigh: " + ", ".join(tiny)
                    + " - a stock solution is recommended.")
    if add_vol_mL > volume_mL * 0.2:
        warn.append("The additives exceed 20% of the total volume. Please check the input.")

    summary = [
        f"Blend ratio : {ratio_txt}   ({', '.join(n for n, _ in mats)})",
        f"Total volume : {volume_mL:g} mL"
        + (f" · total concentration {total_conc_mgml:g} mg/mL"
           if total_conc_mgml is not None else ""),
        f"Total solid mass : {total_solid:.3f} mg",
        f"Solvent volume : {(volume_mL - add_vol_mL) * 1000:.1f} µL"
        + (f" ({add_vol_mL * 1000:.1f} µL of additives subtracted)" if add_vol_mL else ""),
    ]
    return Recipe(rows, summary, warn)


def mgml_to_molar(mgml: float, mw: float) -> float:
    """mg/mL -> mol/L"""
    if mw <= 0:
        raise CalcError("The molar mass must be greater than 0.")
    return mgml / mw


def molar_to_mgml(molar: float, mw: float) -> float:
    """mol/L -> mg/mL"""
    return molar * mw


def dilution(c1: float, v1: float | None, c2: float, v2: float | None) -> tuple[float, float]:
    """Solve C1·V1 = C2·V2 for the missing value. Returns (v1, v2)."""
    if c1 <= 0 or c2 <= 0:
        raise CalcError("Concentrations must be greater than 0.")
    if v2 is not None and v1 is None:
        if c2 > c1:
            raise CalcError("The diluted concentration cannot exceed the stock concentration.")
        return c2 * v2 / c1, v2
    if v1 is not None and v2 is None:
        return v1, c1 * v1 / c2
    raise CalcError("Leave exactly one of V1 or V2 empty.")


def from_stock(stock_conc: float, target_conc: float, target_vol: float) -> tuple[float, float]:
    """Stock -> target concentration/volume. Returns (stock volume, solvent volume)."""
    v_stock, _ = dilution(stock_conc, None, target_conc, target_vol)
    return v_stock, target_vol - v_stock
