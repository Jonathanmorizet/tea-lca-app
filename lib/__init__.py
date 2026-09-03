"""TEA–LCA Christmas-tree optimization helpers.

Library modules import without Streamlit. Pages live under ../pages/.
"""

from .defaults import (
    GWP_COL,
    SCALE_KEYWORDS,
    TRACI_IMPACT_COLS,
    default_farm_config,
)
from .data_model import (
    build_optimizer_arrays,
    inventory_table_for_editor,
    load_deap_excel,
)
from .optimize import (
    apply_individual,
    evaluate_budget_constrained,
    evaluate_compliance_constrained,
    evaluate_cost_gwp_constrained,
    evaluate_cost_only_constrained,
    evaluate_single_impact_constrained,
    run_nsga2_constrained,
    run_single_constrained,
)
from .results import decision_card, hotspot_tables, per_tree_metrics

__all__ = [
    "GWP_COL",
    "SCALE_KEYWORDS",
    "TRACI_IMPACT_COLS",
    "default_farm_config",
    "inventory_table_for_editor",
    "build_optimizer_arrays",
    "load_deap_excel",
    "apply_individual",
    "evaluate_cost_gwp_constrained",
    "evaluate_budget_constrained",
    "evaluate_compliance_constrained",
    "evaluate_cost_only_constrained",
    "evaluate_single_impact_constrained",
    "run_nsga2_constrained",
    "run_single_constrained",
    "decision_card",
    "hotspot_tables",
    "per_tree_metrics",
]
