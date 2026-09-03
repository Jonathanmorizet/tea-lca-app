"""Part 1: farmer-friendly farm workbook."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from lib.data_model import (
    apply_factors_csv,
    baseline_totals,
    build_optimizer_arrays,
    default_farm_config,
    inventory_table_for_editor,
    load_deap_excel,
)
from lib.defaults import GWP_COL, auto_harvested

st.set_page_config(page_title="Farm Setup", page_icon="🚜", layout="wide")
st.title("Farm setup")
st.caption("Acres, rotation, density, and an editable NC Fraser fir enterprise budget")

if "farm_config" not in st.session_state:
    st.session_state.farm_config = default_farm_config()
if "inventory_df" not in st.session_state:
    st.session_state.inventory_df = inventory_table_for_editor()
if "opt_ready" not in st.session_state:
    st.session_state.opt_ready = False
if "source" not in st.session_state:
    st.session_state.source = "workbook"
if "inv_gen" not in st.session_state:
    st.session_state.inv_gen = 0

cfg = dict(st.session_state.farm_config)

st.subheader("Farm size and rotation")
c1, c2, c3 = st.columns(3)
with c1:
    cfg["acres"] = st.number_input("Acres in this block", min_value=0.1, max_value=5000.0, value=float(cfg["acres"]), step=0.5)
with c2:
    cfg["rotation_years"] = st.selectbox("Rotation length (years)", [6, 7, 8], index=[6, 7, 8].index(int(cfg.get("rotation_years", 8))))
with c3:
    cfg["functional_unit"] = st.selectbox(
        "Report results per",
        ["acre_rotation", "harvested_tree"],
        index=0 if cfg.get("functional_unit") == "acre_rotation" else 1,
        format_func=lambda x: "Acre, full rotation" if x == "acre_rotation" else "One harvested tree",
    )

st.subheader("Planting density and harvest")
d1, d2, d3 = st.columns(3)
with d1:
    cfg["planted_per_acre"] = st.number_input("Trees planted per acre", min_value=100, max_value=5000, value=int(cfg["planted_per_acre"]), step=10)
with d2:
    cfg["survival_pct"] = st.number_input("Survival to harvest (%)", min_value=10.0, max_value=100.0, value=float(cfg["survival_pct"]), step=0.5)
auto_h = auto_harvested(cfg["planted_per_acre"], cfg["survival_pct"])
with d3:
    override = st.checkbox("Override harvested trees / acre", value=True, help="NC baseline in the manuscript is 1,900 harvested from 2,150 planted.")
    if override:
        cfg["harvested_per_acre"] = st.number_input("Harvested trees per acre", min_value=50, max_value=5000, value=int(cfg.get("harvested_per_acre", 1900)), step=10)
    else:
        cfg["harvested_per_acre"] = float(auto_h)
        st.metric("Harvested trees / acre (auto)", f"{cfg['harvested_per_acre']:.0f}")

basis = st.session_state.farm_config.get("amount_basis", "per_acre_rotation")
if basis == "workbook_total":
    amt_note = "Excel Amount column is used as-is (workbook total; not multiplied by acres)."
else:
    amt_note = (
        f"Inventory amounts are per acre per {cfg['rotation_years']}-year rotation, "
        "then multiplied by acres."
    )
st.caption(
    f"Baseline trees in the optimizer = acres × harvested/acre = "
    f"**{cfg['acres'] * cfg['harvested_per_acre']:,.0f}** trees. {amt_note}"
)

st.subheader("Enterprise budget and TRACI factors")
st.markdown(
    "Edit **Amount** (per acre, per rotation), **Unit Cost ($)**, and impact factors. "
    f"The climate column must stay named `{GWP_COL}`. Type: Scale (moves with tree count), "
    "Efficiency (fertilizer, diesel, sprays), or Fixed (labor hours)."
)

edited = st.data_editor(
    st.session_state.inventory_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"inventory_editor_{st.session_state.inv_gen}",
    column_config={
        "Amount": st.column_config.NumberColumn(format="%.4f"),
        "Unit Cost ($)": st.column_config.NumberColumn(format="%.3f"),
        "Type": st.column_config.SelectboxColumn(options=["Scale", "Efficiency", "Fixed"]),
    },
)
st.session_state.inventory_df = edited

b1, b2, b3 = st.columns(3)
with b1:
    if st.button("Reset to NC defaults"):
        st.session_state.farm_config = default_farm_config()
        st.session_state.inventory_df = inventory_table_for_editor()
        st.session_state.source = "workbook"
        st.session_state.opt_ready = False
        st.session_state.inv_gen += 1
        st.rerun()
with b2:
    csv_file = st.file_uploader("Load factors CSV", type=["csv"], help="Columns: Material, Unit, Unit Cost ($), kg CO2-Eq/Unit, …")
    if csv_file is not None:
        fid = (csv_file.name, csv_file.size)
        if st.session_state.get("_csv_id") != fid:
            try:
                factors = pd.read_csv(csv_file)
                st.session_state.inventory_df = apply_factors_csv(st.session_state.inventory_df, factors)
                st.session_state._csv_id = fid
                st.session_state.inv_gen += 1
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read factors CSV: {exc}")
with b3:
    xlsm = st.file_uploader("DEAP .xlsm (power user)", type=["xlsm", "xlsx"], help="Sheet 0 = inputs (Amount), sheet 1 = costs, sheet 2 = TRACI. Join on Material + Unit.")
    if xlsm is not None:
        fid = (xlsm.name, xlsm.size)
        if st.session_state.get("_xlsm_id") != fid:
            try:
                loaded = load_deap_excel(xlsm)
                st.session_state.inventory_df = loaded["inventory_df"]
                farm = loaded["farm_config"]
                farm["acres"] = cfg["acres"]
                farm["rotation_years"] = cfg["rotation_years"]
                farm["planted_per_acre"] = cfg["planted_per_acre"]
                farm["survival_pct"] = cfg["survival_pct"]
                farm["harvested_per_acre"] = cfg["harvested_per_acre"]
                farm["functional_unit"] = cfg["functional_unit"]
                st.session_state.farm_config = farm
                st.session_state.source = "excel"
                st.session_state._xlsm_id = fid
                st.session_state.inv_gen += 1
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read Excel: {exc}")

# Keep live farm_config (except excel amount_basis already set)
if st.session_state.source != "excel":
    cfg["amount_basis"] = "per_acre_rotation"
    st.session_state.farm_config = cfg
else:
    # acres / density still apply to baseline_trees
    live = dict(st.session_state.farm_config)
    for k in ("acres", "rotation_years", "planted_per_acre", "survival_pct", "harvested_per_acre", "functional_unit"):
        live[k] = cfg[k]
    st.session_state.farm_config = live

try:
    arrays = build_optimizer_arrays(st.session_state.farm_config, st.session_state.inventory_df)
    tot = baseline_totals(arrays)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Baseline trees", f"{tot['trees']:,.0f}")
    m2.metric("Baseline cost", f"${tot['total_cost']:,.0f}")
    m3.metric("Baseline GWP", f"{tot['total_gwp']:,.0f} kg CO2-eq")
    m4.metric("Per harvested tree", f"${tot['cost_per_tree']:.2f}  |  {tot['gwp_per_tree']:.2f} kg")
    st.caption(f"Source: {st.session_state.source}. Scale materials: {int(arrays['scale_mask'].sum())}. Efficiency: {int(arrays['efficiency_mask'].sum())}.")
except Exception as exc:
    arrays = None
    st.warning(f"Inventory is not ready: {exc}")

if st.button("Save & continue to Optimize", type="primary", disabled=arrays is None):
    st.session_state.opt_ready = True
    st.session_state.opt_arrays = arrays
    st.success("Saved. Open **Optimize** in the sidebar.")
    st.page_link("pages/2_Optimize.py", label="Continue to Optimize", icon="📈")
