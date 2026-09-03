"""Part 2: grower-language optimization UI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st

from lib.data_model import baseline_totals, build_optimizer_arrays
from lib.defaults import GWP_COL
from lib.optimize import (
    apply_individual,
    evaluate_budget_constrained,
    evaluate_compliance_constrained,
    evaluate_cost_only_constrained,
    evaluate_single_impact_constrained,
    run_nsga2_constrained,
    run_single_constrained,
)
from lib.results import (
    decision_card,
    excel_bytes,
    gwp_vector,
    hotspot_tables,
    knee_index,
    material_change_table,
    metrics_for_ind,
    pareto_dataframe,
    plot_budget,
    plot_cost_gwp,
)

st.set_page_config(page_title="Optimize", page_icon="📈", layout="wide")
st.title("Optimize the farm plan")

if not st.session_state.get("opt_ready"):
    st.warning("Save a farm inventory first.")
    st.page_link("pages/1_Farm_Setup.py", label="Go to Farm Setup", icon="🚜")
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []

try:
    arrays = build_optimizer_arrays(st.session_state.farm_config, st.session_state.inventory_df)
except Exception as exc:
    st.error(f"Could not build optimizer arrays: {exc}")
    st.stop()

base = baseline_totals(arrays)
gwp_u = gwp_vector(arrays)
materials = arrays["materials"]
traci_cols = arrays["traci_impact_cols"]

st.info(
    f"Baseline **{base['trees']:,.0f} trees**: ${base['total_cost']:,.0f} total "
    f"(${base['cost_per_tree']:.2f}/tree) · {base['total_gwp']:,.0f} kg CO2-eq "
    f"({base['gwp_per_tree']:.2f} kg/tree). Source: {st.session_state.get('source', 'workbook')}."
)

GOALS = {
    "Show cost vs carbon tradeoffs": "tradeoff",
    "Max trees under my budget": "budget",
    "Cut carbon by X% at lowest cost": "compliance",
    "Lowest cost only": "cost",
    "Minimize one environmental impact": "impact",
}
goal_label = st.selectbox("What do you want the tool to do?", list(GOALS.keys()))
goal = GOALS[goal_label]

budget_limit = None
gwp_reduction_pct = 15
selected_impact = GWP_COL if GWP_COL in traci_cols else (traci_cols[0] if traci_cols else GWP_COL)

if goal == "budget":
    budget_limit = st.number_input(
        "Season / rotation budget ($)",
        min_value=float(base["total_cost"] * 0.5),
        max_value=float(base["total_cost"] * 2.0),
        value=float(base["total_cost"]),
        step=100.0,
    )
elif goal == "compliance":
    gwp_reduction_pct = st.slider("Cut carbon by (%)", 0, 50, 15, 5)
    st.caption(f"Target GWP ≤ {base['total_gwp'] * (1 - gwp_reduction_pct / 100):,.1f} kg CO2-eq")
elif goal == "impact":
    selected_impact = st.selectbox("Which impact to minimize?", traci_cols)

with st.expander("Advanced — genetic algorithm and material types", expanded=False):
    a1, a2, a3, a4 = st.columns(4)
    popsize = a1.slider("Population size", 20, 200, 80)
    ngen = a2.slider("Generations", 10, 200, 40)
    cxpb = a3.slider("Crossover probability", 0.0, 1.0, 0.7)
    mutpb = a4.slider("Mutation probability", 0.0, 1.0, 0.3)
    b1, b2 = st.columns(2)
    max_scale_pct = b1.slider("Production (tree count) ±%", 0, 30, 10)
    max_eff_pct = b2.slider("Input efficiency ±%", 5, 30, 20)
    st.markdown("Override which inputs scale with trees vs. can be used more/less efficiently.")
    scale_idx = st.multiselect(
        "SCALE (moves with tree count)",
        options=list(range(len(materials))),
        default=list(np.where(arrays["scale_mask"])[0]),
        format_func=lambda i: materials[i],
    )
    remaining = [i for i in range(len(materials)) if i not in scale_idx]
    default_eff = [i for i in remaining if arrays["efficiency_mask"][i]]
    eff_idx = st.multiselect(
        "EFFICIENCY (fertilizer, diesel, sprays)",
        options=remaining,
        default=default_eff,
        format_func=lambda i: materials[i],
    )
    seed = st.number_input("Random seed (optional, 0 = unset)", min_value=0, value=42, step=1)

scale_mask = np.zeros(len(materials), dtype=bool)
scale_mask[scale_idx] = True
efficiency_mask = np.zeros(len(materials), dtype=bool)
efficiency_mask[eff_idx] = True
arrays = dict(arrays)
arrays["scale_mask"] = scale_mask
arrays["efficiency_mask"] = efficiency_mask
max_scale_dev = max_scale_pct / 100.0
max_eff_dev = max_eff_pct / 100.0
seed_arg = int(seed) if seed else None

ga = dict(popsize=popsize, ngen=ngen, cxpb=cxpb, mutpb=mutpb)


def _change_table(amounts):
    return material_change_table(
        materials,
        arrays["base_amounts"],
        amounts,
        arrays["costs"],
        gwp_u,
        scale_mask,
        efficiency_mask,
    )


def _show_card_and_hotspots(amounts, title="Selected plan"):
    st.markdown(f"### {title}")
    st.markdown(decision_card(materials, arrays["base_amounts"], amounts, arrays["costs"], gwp_u))
    cost_h, gwp_h = hotspot_tables(materials, amounts, arrays["costs"], gwp_u)
    h1, h2 = st.columns(2)
    with h1:
        st.markdown("**Top cost drivers**")
        st.dataframe(cost_h, use_container_width=True)
    with h2:
        st.markdown("**Top carbon drivers**")
        st.dataframe(gwp_h, use_container_width=True)
    return cost_h, gwp_h


if st.button("Run optimization", type="primary"):
    with st.spinner("Searching farm plans…"):
        try:
            if goal == "tradeoff":
                front = run_nsga2_constrained(
                    ga["popsize"], ga["ngen"], ga["cxpb"], ga["mutpb"],
                    arrays["costs"], arrays["impact_matrix"], traci_cols,
                    arrays["base_amounts"], arrays["baseline_trees"],
                    scale_mask, efficiency_mask, max_scale_dev, max_eff_dev,
                    seed=seed_arg,
                )
                df_p = pareto_dataframe(front, arrays)
                st.session_state.last_run = {
                    "kind": "pareto", "goal": goal_label, "df": df_p, "budget": None, "fresh": True,
                }
            elif goal == "budget":
                front = run_nsga2_constrained(
                    ga["popsize"], ga["ngen"], ga["cxpb"], ga["mutpb"],
                    arrays["costs"], arrays["impact_matrix"], traci_cols,
                    arrays["base_amounts"], arrays["baseline_trees"],
                    scale_mask, efficiency_mask, max_scale_dev, max_eff_dev,
                    eval_func=evaluate_budget_constrained,
                    budget_limit=budget_limit,
                    seed=seed_arg,
                )
                df_p = pareto_dataframe(front, arrays)
                df_p = df_p[df_p["Total Cost"] <= budget_limit + 1e-6].reset_index(drop=True)
                st.session_state.last_run = {
                    "kind": "budget", "goal": goal_label, "df": df_p, "budget": budget_limit, "fresh": True,
                }
            elif goal == "compliance":
                target = base["total_gwp"] * (1 - gwp_reduction_pct / 100.0)
                best = run_single_constrained(
                    evaluate_compliance_constrained, ga["popsize"], ga["ngen"], ga["cxpb"], ga["mutpb"],
                    arrays["base_amounts"], arrays["baseline_trees"],
                    scale_mask, efficiency_mask, max_scale_dev, max_eff_dev,
                    arrays["costs"], arrays["impact_matrix"], traci_cols,
                    gwp_target=target, seed=seed_arg,
                )
                st.session_state.last_run = {
                    "kind": "single", "goal": goal_label, "ind": list(best),
                    "target": target, "pct": gwp_reduction_pct, "fresh": True,
                }
            elif goal == "cost":
                best = run_single_constrained(
                    evaluate_cost_only_constrained, ga["popsize"], ga["ngen"], ga["cxpb"], ga["mutpb"],
                    arrays["base_amounts"], arrays["baseline_trees"],
                    scale_mask, efficiency_mask, max_scale_dev, max_eff_dev,
                    arrays["costs"], seed=seed_arg,
                )
                st.session_state.last_run = {"kind": "single", "goal": goal_label, "ind": list(best), "fresh": True}
            else:
                best = run_single_constrained(
                    evaluate_single_impact_constrained, ga["popsize"], ga["ngen"], ga["cxpb"], ga["mutpb"],
                    arrays["base_amounts"], arrays["baseline_trees"],
                    scale_mask, efficiency_mask, max_scale_dev, max_eff_dev,
                    arrays["impact_matrix"], selected_impact, traci_cols,
                    seed=seed_arg,
                )
                st.session_state.last_run = {
                    "kind": "single", "goal": goal_label, "ind": list(best), "impact": selected_impact, "fresh": True,
                }
        except Exception as exc:
            st.exception(exc)
            st.stop()

run = st.session_state.get("last_run")
if not run:
    st.caption("Choose a goal and click **Run optimization**.")
    st.stop()

st.subheader(run["goal"])

if run["kind"] in ("pareto", "budget"):
    df_p = run["df"]
    if df_p is None or df_p.empty:
        st.error("No feasible plans found. Loosen the budget or Advanced bounds.")
        st.stop()
    show = df_p.drop(columns=["Individual"], errors="ignore")
    st.dataframe(show, use_container_width=True)
    if run["kind"] == "budget":
        fig = plot_budget(df_p, run["budget"], base["total_cost"], base["trees"], base["total_gwp"])
        best_i = int(df_p["Trees"].idxmax())
        st.success(
            f"Most trees on budget: **{int(df_p.loc[best_i, 'Trees']):,}** "
            f"for ${df_p.loc[best_i, 'Total Cost']:,.0f}."
        )
    else:
        fig = plot_cost_gwp(df_p, base["total_cost"], base["total_gwp"], base["trees"])
        best_i = knee_index(df_p)
        st.success(
            f"Balanced plan (knee): **{int(df_p.loc[best_i, 'Trees']):,} trees**, "
            f"${df_p.loc[best_i, 'Total Cost']:,.0f}, {df_p.loc[best_i, 'Total GWP']:,.0f} kg CO2-eq."
        )
    st.pyplot(fig)

    labels = [
        f"Plan {i+1}: {int(r.Trees)} trees, ${r['Total Cost']:,.0f}, {r['Total GWP']:,.0f} kg"
        for i, r in df_p.iterrows()
    ]
    pick = st.selectbox("Inspect a plan", range(len(df_p)), index=int(best_i), format_func=lambda i: labels[i])
    row = df_p.iloc[pick]
    amounts, _ = apply_individual(row["Individual"], arrays["base_amounts"], scale_mask, efficiency_mask)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Trees", f"{int(row['Trees']):,}")
    k2.metric("Cost", f"${row['Total Cost']:,.0f}", f"{(row['Total Cost']/base['total_cost']-1)*100:+.1f}%")
    k3.metric("GWP", f"{row['Total GWP']:,.0f} kg", f"{(row['Total GWP']/max(base['total_gwp'],1e-9)-1)*100:+.1f}%")
    k4.metric("Per tree", f"${row['Cost/Tree']:.2f} | {row['GWP/Tree']:.2f} kg")
    change = _change_table(amounts)
    st.markdown("### Material changes")
    st.dataframe(change, use_container_width=True)
    cost_h, gwp_h = _show_card_and_hotspots(amounts)
    hist_df = change
    pareto_out = df_p
else:
    ind = run["ind"]
    m = metrics_for_ind(ind, arrays)
    amounts = m["amounts"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Trees", f"{int(m['trees']):,}", f"{(m['trees']/base['trees']-1)*100:+.1f}%")
    k2.metric("Cost", f"${m['total_cost']:,.0f}", f"{(m['total_cost']/base['total_cost']-1)*100:+.1f}%")
    k3.metric("GWP", f"{m['total_gwp']:,.0f} kg", f"{(m['total_gwp']/max(base['total_gwp'],1e-9)-1)*100:+.1f}%")
    k4.metric("Per tree", f"${m['cost_per_tree']:.2f} | {m['gwp_per_tree']:.2f} kg")
    if "target" in run:
        if m["total_gwp"] <= run["target"] * 1.01:
            st.success(f"Carbon target met ({run['pct']}% cut). GWP {m['total_gwp']:,.1f} ≤ {run['target']:,.1f}.")
        else:
            st.warning(f"Best attempt {m['total_gwp']:,.1f} kg vs target {run['target']:,.1f}. Raise generations or efficiency ±%.")
        extra = m["total_cost"] - base["total_cost"]
        saved = base["total_gwp"] - m["total_gwp"]
        if saved > 0:
            st.caption(f"Cost of carbon cut: ${extra:,.0f} for {saved:,.1f} kg → ${extra/saved:.2f} per kg CO2-eq.")
    change = _change_table(amounts)
    st.markdown("### Material changes")
    st.dataframe(change, use_container_width=True)
    cost_h, gwp_h = _show_card_and_hotspots(amounts)
    hist_df = change
    pareto_out = None

if run["kind"] in ("pareto", "budget"):
    metrics = {
        "goal": run["goal"],
        "trees": float(row["Trees"]),
        "total_cost": float(row["Total Cost"]),
        "total_gwp": float(row["Total GWP"]),
        "cost_per_tree": float(row["Cost/Tree"]),
        "gwp_per_tree": float(row["GWP/Tree"]),
    }
else:
    metrics = {k: m[k] for k in ("trees", "total_cost", "total_gwp", "cost_per_tree", "gwp_per_tree")}
    metrics["goal"] = run["goal"]

st.download_button(
    "Download Excel",
    data=excel_bytes(st.session_state.inventory_df, change, metrics, pareto_out, cost_h, gwp_h),
    file_name="tea_lca_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

if run.pop("fresh", False):
    st.session_state.history.append(
        {"scenario": run["goal"], "results": hist_df.drop(columns=["Individual"], errors="ignore")}
    )

with st.expander("Optimization history"):
    if st.session_state.history:
        for i, rec in enumerate(st.session_state.history, 1):
            st.write(f"**Run {i}: {rec['scenario']}**")
            st.dataframe(rec["results"], use_container_width=True)
    else:
        st.caption("No runs recorded yet.")
