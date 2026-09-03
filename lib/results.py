"""Decision card, hotspots, per-tree metrics, Excel export, and plots."""

from __future__ import annotations

from io import BytesIO
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .defaults import GWP_COL
from .optimize import apply_individual


def per_tree_metrics(total_cost: float, total_gwp: float, trees: float) -> dict[str, float]:
    t = max(float(trees), 1e-9)
    return {
        "trees": float(trees),
        "total_cost": float(total_cost),
        "total_gwp": float(total_gwp),
        "cost_per_tree": float(total_cost) / t,
        "gwp_per_tree": float(total_gwp) / t,
    }


def type_labels(scale_mask: np.ndarray, efficiency_mask: np.ndarray) -> list[str]:
    labels = []
    for s, e in zip(scale_mask, efficiency_mask):
        if s:
            labels.append("SCALE")
        elif e:
            labels.append("EFFICIENCY")
        else:
            labels.append("FIXED")
    return labels


def material_change_table(
    materials: Sequence[str],
    base: np.ndarray,
    opt: np.ndarray,
    costs: np.ndarray,
    gwp_per_unit: Optional[np.ndarray] = None,
    scale_mask: Optional[np.ndarray] = None,
    efficiency_mask: Optional[np.ndarray] = None,
) -> pd.DataFrame:
    base = np.asarray(base, dtype=float).flatten()
    opt = np.asarray(opt, dtype=float).flatten()
    costs = np.asarray(costs, dtype=float).flatten()
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(np.abs(base) > 1e-12, (opt - base) / base * 100.0, 0.0)
    data = {
        "Material": list(materials),
        "Base Amount": base,
        "Optimized Amount": opt,
        "Change (%)": pct,
        "Cost Impact ($)": (opt - base) * costs,
    }
    if scale_mask is not None and efficiency_mask is not None:
        data["Type"] = type_labels(scale_mask, efficiency_mask)
    if gwp_per_unit is not None:
        gwp_per_unit = np.asarray(gwp_per_unit, dtype=float).flatten()
        data["GWP Impact (kg CO2)"] = (opt - base) * gwp_per_unit
    df = pd.DataFrame(data)
    order = ["Material"]
    if "Type" in df.columns:
        order.append("Type")
    order += ["Base Amount", "Optimized Amount", "Change (%)", "Cost Impact ($)"]
    if "GWP Impact (kg CO2)" in df.columns:
        order.append("GWP Impact (kg CO2)")
    return df[order]


def decision_card(
    materials,
    base,
    opt,
    costs,
    impact_gwp_col,
    n: int = 5,
    min_pct: float = 0.5,
) -> str:
    """Markdown bullets of biggest % cuts/increases with $ and kg CO2."""
    base = np.asarray(base, dtype=float).flatten()
    opt = np.asarray(opt, dtype=float).flatten()
    costs = np.asarray(costs, dtype=float).flatten()
    gwp_u = np.asarray(impact_gwp_col, dtype=float).flatten()
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(np.abs(base) > 1e-12, (opt - base) / base * 100.0, 0.0)
    d_cost = (opt - base) * costs
    d_gwp = (opt - base) * gwp_u
    rows = []
    for i, name in enumerate(materials):
        if abs(pct[i]) < min_pct:
            continue
        rows.append((abs(pct[i]), i, name, pct[i], d_cost[i], d_gwp[i]))
    rows.sort(reverse=True)
    if not rows:
        return (
            "No material moved more than {:.1f}% from the baseline. "
            "Try widening the Advanced efficiency or scale bounds."
        ).format(min_pct)

    lines = ["**What to change (largest moves vs your baseline)**"]
    for _, _i, name, p, dc, dg in rows[:n]:
        direction = "cut" if p < 0 else "increase"
        lines.append(
            f"- **{name}**: {direction} by {abs(p):.1f}% "
            f"({dc:+,.0f} $, {dg:+,.1f} kg CO2-eq)"
        )
    return "\n".join(lines)


def hotspot_tables(
    materials,
    amounts,
    costs,
    gwp_per_unit,
    top_n: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two small DataFrames: top cost drivers and top GWP drivers."""
    amounts = np.asarray(amounts, dtype=float).flatten()
    costs = np.asarray(costs, dtype=float).flatten()
    gwp_u = np.asarray(gwp_per_unit, dtype=float).flatten()
    cost_tot = amounts * costs
    gwp_tot = amounts * gwp_u
    cost_sum = float(cost_tot.sum()) or 1.0
    gwp_sum = float(np.abs(gwp_tot).sum()) or 1.0
    cost_df = pd.DataFrame(
        {
            "Material": list(materials),
            "Cost ($)": cost_tot,
            "Share (%)": cost_tot / cost_sum * 100.0,
        }
    ).sort_values("Cost ($)", ascending=False).head(top_n)
    gwp_df = pd.DataFrame(
        {
            "Material": list(materials),
            "GWP (kg CO2-eq)": gwp_tot,
            "Share (%)": np.abs(gwp_tot) / gwp_sum * 100.0,
        }
    ).sort_values("GWP (kg CO2-eq)", ascending=False).head(top_n)
    return cost_df.reset_index(drop=True), gwp_df.reset_index(drop=True)


def gwp_vector(arrays: dict) -> np.ndarray:
    cols = arrays["traci_impact_cols"]
    matrix = np.asarray(arrays["impact_matrix"], dtype=float)
    if GWP_COL in cols:
        return matrix[:, cols.index(GWP_COL)].flatten()
    return np.zeros(len(arrays["materials"]), dtype=float)


def metrics_for_ind(ind, arrays: dict) -> dict:
    amounts, scale = apply_individual(
        ind, arrays["base_amounts"], arrays["scale_mask"], arrays["efficiency_mask"]
    )
    trees = float(arrays["baseline_trees"]) * scale
    cost = float(np.dot(amounts, arrays["costs"]))
    gwp = float(np.dot(amounts, gwp_vector(arrays)))
    m = per_tree_metrics(cost, gwp, trees)
    m["production_scale"] = scale
    m["amounts"] = amounts
    m["individual"] = list(ind)
    return m


def pareto_dataframe(front, arrays: dict) -> pd.DataFrame:
    rows = []
    for ind in front:
        m = metrics_for_ind(ind, arrays)
        rows.append(
            {
                "Trees": int(round(m["trees"])),
                "Total Cost": m["total_cost"],
                "Total GWP": m["total_gwp"],
                "Cost/Tree": m["cost_per_tree"],
                "GWP/Tree": m["gwp_per_tree"],
                "Production Scale": m["production_scale"],
                "Individual": m["individual"],
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("Total Cost").reset_index(drop=True)


def knee_index(df: pd.DataFrame, x="Total Cost", y="Total GWP") -> int:
    """Point closest to the normalized origin (cheap and low carbon)."""
    if df.empty:
        return 0
    xs = df[x].to_numpy(dtype=float)
    ys = df[y].to_numpy(dtype=float)
    xr = xs.max() - xs.min() or 1.0
    yr = ys.max() - ys.min() or 1.0
    xn = (xs - xs.min()) / xr
    yn = (ys - ys.min()) / yr
    return int(np.argmin(np.hypot(xn, yn)))


def plot_cost_gwp(df: pd.DataFrame, baseline_cost: float, baseline_gwp: float, baseline_trees: float):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))
    sc = ax1.scatter(df["Total Cost"], df["Total GWP"], c=df["Trees"], cmap="viridis", s=70, alpha=0.85)
    ax1.scatter([baseline_cost], [baseline_gwp], color="red", s=160, marker="*", label="Baseline", zorder=5)
    ax1.set_xlabel("Total cost ($)")
    ax1.set_ylabel("Total GWP (kg CO2-eq)")
    ax1.set_title("Tradeoff: farm total")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    fig.colorbar(sc, ax=ax1, label="Trees")

    ax2.scatter(df["Cost/Tree"], df["GWP/Tree"], c=df["Trees"], cmap="viridis", s=70, alpha=0.85)
    ax2.scatter(
        [baseline_cost / max(baseline_trees, 1e-9)],
        [baseline_gwp / max(baseline_trees, 1e-9)],
        color="red",
        s=160,
        marker="*",
        label="Baseline",
        zorder=5,
    )
    ax2.set_xlabel("Cost per tree ($)")
    ax2.set_ylabel("GWP per tree (kg CO2-eq)")
    ax2.set_title("Tradeoff: per harvested tree")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_budget(df: pd.DataFrame, budget: float, baseline_cost: float, baseline_trees: float, baseline_gwp: float):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.6))
    sc1 = ax1.scatter(df["Total Cost"], df["Trees"], c=df["Total GWP"], cmap="RdYlGn_r", s=80, alpha=0.85)
    ax1.axvline(budget, color="red", linestyle="--", label=f"Budget ${budget:,.0f}")
    ax1.scatter([baseline_cost], [baseline_trees], color="red", s=160, marker="*", label="Baseline", zorder=5)
    ax1.set_xlabel("Total cost ($)")
    ax1.set_ylabel("Harvested trees")
    ax1.set_title("Budget solutions (color = GWP)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    fig.colorbar(sc1, ax=ax1, label="Total GWP")

    sc2 = ax2.scatter(df["Trees"], df["Total GWP"], c=df["Total Cost"], cmap="viridis", s=80, alpha=0.85)
    ax2.scatter([baseline_trees], [baseline_gwp], color="red", s=160, marker="*", label="Baseline", zorder=5)
    ax2.set_xlabel("Harvested trees")
    ax2.set_ylabel("Total GWP (kg CO2-eq)")
    ax2.set_title("Trees vs carbon (color = cost)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    fig.colorbar(sc2, ax=ax2, label="Total cost ($)")
    fig.tight_layout()
    return fig


def excel_bytes(
    inventory_df: pd.DataFrame,
    change_df: pd.DataFrame,
    metrics: dict,
    pareto_df: Optional[pd.DataFrame] = None,
    cost_hot: Optional[pd.DataFrame] = None,
    gwp_hot: Optional[pd.DataFrame] = None,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        inventory_df.to_excel(writer, index=False, sheet_name="Inventory")
        change_df.to_excel(writer, index=False, sheet_name="Material changes")
        pd.DataFrame([metrics]).to_excel(writer, index=False, sheet_name="Metrics")
        if pareto_df is not None and not pareto_df.empty:
            show = pareto_df.drop(columns=["Individual"], errors="ignore")
            show.to_excel(writer, index=False, sheet_name="Pareto")
        if cost_hot is not None:
            cost_hot.to_excel(writer, index=False, sheet_name="Cost hotspots")
        if gwp_hot is not None:
            gwp_hot.to_excel(writer, index=False, sheet_name="GWP hotspots")
    output.seek(0)
    return output.getvalue()
