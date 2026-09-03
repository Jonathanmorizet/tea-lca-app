"""Fraser fir TEA–LCA optimizer — home page."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Christmas Tree TEA–LCA",
    page_icon="🌲",
    layout="wide",
)

st.title("Christmas tree TEA–LCA optimizer")
st.caption("Fraser fir farm workbook → cost vs carbon tradeoffs for NC growers")

st.markdown(
    """
This app is for **Christmas tree growers and advisors** who want to see how
planting density, fertilizer, pesticides, and diesel use trade off against
**operating cost** and **carbon (GWP)**.

### Two steps
1. **Farm Setup** — enter acres, rotation length, planting density, and an
   enterprise-budget inventory. NC Fraser fir defaults are loaded for you and
   every cost and factor is editable.
2. **Optimize** — pick a grower goal (tradeoffs, stay on budget, cut carbon,
   lowest cost). Genetic-algorithm knobs stay under **Advanced**.

Use the sidebar pages to move between steps.

### Two ways to load data
- **Workbook (default):** type farm numbers and edit the inventory table.
- **Excel power-user path:** upload a DEAP-readable `.xlsm` with three sheets
  (inputs, unit costs, TRACI factors) joined on Material + Unit — the original
  workflow still works.

### Disclaimer — TRACI stubs are not ecoinvent
Starter climate, acidification, and eutrophication factors are **placeholders**
so the optimizer can run before a licensed ecoinvent/openLCA export is linked.
Do not treat stub kg CO2-eq as a published LCA result. Replace them with your
TRACI 2.1 factors (Farm Setup → Load factors CSV, or the `.xlsm` upload).
"""
)

col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/1_Farm_Setup.py", label="Go to Farm Setup", icon="🚜")
with col2:
    st.page_link("pages/2_Optimize.py", label="Go to Optimize", icon="📈")

st.info(
    "Results are a screening TEA–LCA, not a certified EPD. Functional units are "
    "one acre over a rotation or one harvested 7-ft tree."
)
