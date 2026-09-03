# Christmas tree TEA–LCA optimizer

Farmer-facing Streamlit app that turns a Fraser fir **farm workbook**
(acres, rotation, density, enterprise-budget costs) into a **cost vs carbon**
search. The original DEAP/NSGA-II engine is unchanged in spirit: production
scale + input efficiency, Pareto or single-objective, budget and GWP-target
constraints.

## Run

```bash
cd tea-lca-app
python -m pip install -r requirements.txt
streamlit run Home.py
```

Then open **Farm Setup**, review or edit the NC defaults, click
**Save & continue to Optimize**, pick a grower goal, and run.

## Two data paths

| Path | Who | What happens |
|------|-----|----------------|
| Workbook (default) | Grower | Amounts are **per acre per rotation**, multiplied by acres. Baseline trees = acres × harvested trees/acre (NC default 1,900). |
| DEAP `.xlsm` | Power user | Same merge as the original app: sheet 0 = inputs (`Amount`), sheet 1 = unit costs, sheet 2 = TRACI factors, joined on **Material + Unit**. Amounts are used as workbook totals (not re-multiplied by acres). |

A factors CSV (`data/sample_factors.csv`) can replace unit costs and TRACI
columns without changing amounts.

## Grower goals (NSGA stays under Advanced)

- Show cost vs carbon tradeoffs
- Max trees under my budget
- Cut carbon by X% at lowest cost
- Lowest cost only
- Minimize one environmental impact

Advanced expander: population, generations, crossover/mutation, scale ±%,
efficiency ±%, and Scale vs Efficiency vs Fixed material overrides.

## Stub TRACI caveat

Starter climate (`kg CO2-Eq/Unit`), acidification, eutrophication, and
ecotoxicity values are **placeholders** so the optimizer can run before
ecoinvent/openLCA is linked. They are **not** a published LCA result and
must be replaced with licensed TRACI 2.1 factors for any decision that
will be reported.

Unit costs are NC-style enterprise-budget *examples*, also editable.

## Layout

```
tea-lca-app/
  Home.py
  requirements.txt
  lib/           # defaults, data_model, optimize, results  (import without Streamlit)
  pages/         # 1_Farm_Setup.py, 2_Optimize.py
  data/sample_factors.csv
```

## Intentional stubs / later work

- TRACI / ecoinvent factors (see above)
- GI (6- and 7-year) and PRR disease-management scenario switches
- Uncertainty (biomass uptake, price bands)
- PDF / full LCI export beyond Excel
