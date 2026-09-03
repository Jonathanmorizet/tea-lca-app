"""DEAP / NSGA-II evaluation and runners (no Streamlit, no runtime pip).

Individual encoding: [production_scale, efficiency_1, efficiency_2, ...]
Scale materials vary with production_scale only.
Efficiency materials vary with production_scale * efficiency_i (running index).
Fixed materials stay at the baseline amount.

The original cost-vs-GWP / cost-only / single-impact evaluators used
``np.where(efficiency_mask[:i])[0].size`` which is correct, but budget and
compliance already used a running counter. All paths now share apply_individual.
"""

from __future__ import annotations

import random
from typing import Callable, Optional, Sequence

import numpy as np
from deap import base, creator, tools

from .defaults import GWP_COL

_CREATOR_READY = {"nsga": False, "single": False}


def set_seed(seed: Optional[int] = None) -> None:
    if seed is None:
        return
    random.seed(seed)
    np.random.seed(seed)


def apply_individual(
    ind: Sequence[float],
    base_amounts: np.ndarray,
    scale_mask: np.ndarray,
    efficiency_mask: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Decode an individual into material amounts and production_scale."""
    production_scale = float(ind[0])
    efficiency_factors = np.asarray(ind[1:], dtype=float)
    base = np.asarray(base_amounts, dtype=float).flatten()
    scale_mask = np.asarray(scale_mask, dtype=bool).flatten()
    efficiency_mask = np.asarray(efficiency_mask, dtype=bool).flatten()
    final = np.copy(base)
    eff_i = 0
    n_eff = len(efficiency_factors)
    for i in range(len(final)):
        if scale_mask[i]:
            final[i] = base[i] * production_scale
        elif efficiency_mask[i]:
            factor = float(efficiency_factors[eff_i]) if eff_i < n_eff else 1.0
            final[i] = base[i] * production_scale * factor
            eff_i += 1
    return final, production_scale


def _bound_penalty(value: float, lo: float, hi: float, weight: float) -> float:
    if value < lo:
        return weight * abs(value - lo)
    if value > hi:
        return weight * abs(value - hi)
    return 0.0


def _scale_eff_penalties(
    production_scale: float,
    efficiency_factors: np.ndarray,
    max_scale_dev: float,
    max_eff_dev: float,
    weight: float = 10_000.0,
) -> float:
    penalty = _bound_penalty(
        production_scale, 1 - max_scale_dev, 1 + max_scale_dev, weight
    )
    lo, hi = 1 - max_eff_dev, 1 + max_eff_dev
    for ef in np.asarray(efficiency_factors, dtype=float).flatten():
        penalty += _bound_penalty(float(ef), lo, hi, weight)
    return float(penalty)


def _gwp(amounts: np.ndarray, impact_matrix: np.ndarray, impact_cols: Sequence[str]) -> float:
    try:
        idx = list(impact_cols).index(GWP_COL)
    except ValueError:
        return 0.0
    col = np.asarray(impact_matrix, dtype=float)[:, idx].flatten()
    a = np.asarray(amounts, dtype=float).flatten()
    n = min(len(a), len(col))
    return float(np.dot(a[:n], col[:n]))


def _cost(amounts: np.ndarray, costs: np.ndarray) -> float:
    a = np.asarray(amounts, dtype=float).flatten()
    c = np.asarray(costs, dtype=float).flatten()
    n = min(len(a), len(c))
    return float(np.dot(a[:n], c[:n]))


def evaluate_cost_gwp_constrained(
    ind,
    costs,
    impact_matrix,
    impact_cols,
    base_amounts,
    baseline_trees,
    scale_materials_mask,
    efficiency_materials_mask,
    max_scale_deviation,
    max_efficiency_deviation,
):
    """Minimize (cost, GWP)."""
    final, scale = apply_individual(
        ind, base_amounts, scale_materials_mask, efficiency_materials_mask
    )
    penalty = _scale_eff_penalties(
        scale, ind[1:], max_scale_deviation, max_efficiency_deviation
    )
    return _cost(final, costs) + penalty, _gwp(final, impact_matrix, impact_cols) + penalty


def evaluate_budget_constrained(
    ind,
    costs,
    impact_matrix,
    impact_cols,
    base_amounts,
    baseline_trees,
    scale_materials_mask,
    efficiency_materials_mask,
    max_scale_deviation,
    max_efficiency_deviation,
    budget_limit,
):
    """Maximize trees, minimize GWP, subject to budget. Returns (-trees, gwp)."""
    final, scale = apply_individual(
        ind, base_amounts, scale_materials_mask, efficiency_materials_mask
    )
    total_cost = _cost(final, costs)
    penalty = _scale_eff_penalties(
        scale, ind[1:], max_scale_deviation, max_efficiency_deviation
    )
    if total_cost > budget_limit:
        penalty += 100_000.0 * float(total_cost - budget_limit)
    actual_trees = float(baseline_trees) * scale
    gwp = _gwp(final, impact_matrix, impact_cols)
    return float(-actual_trees + penalty), float(gwp + penalty)


def evaluate_compliance_constrained(
    ind,
    costs,
    impact_matrix,
    impact_cols,
    base_amounts,
    baseline_trees,
    scale_materials_mask,
    efficiency_materials_mask,
    max_scale_deviation,
    max_efficiency_deviation,
    gwp_target,
):
    """Minimize cost while meeting a GWP cap. Returns (cost,)."""
    final, scale = apply_individual(
        ind, base_amounts, scale_materials_mask, efficiency_materials_mask
    )
    total_cost = _cost(final, costs)
    gwp = _gwp(final, impact_matrix, impact_cols)
    penalty = _scale_eff_penalties(
        scale, ind[1:], max_scale_deviation, max_efficiency_deviation, weight=100_000.0
    )
    if gwp > gwp_target:
        penalty += 1_000_000.0 * float(gwp - gwp_target)
    return (float(total_cost + penalty),)


def evaluate_cost_only_constrained(
    ind,
    costs,
    base_amounts,
    baseline_trees,
    scale_materials_mask,
    efficiency_materials_mask,
    max_scale_deviation,
    max_efficiency_deviation,
):
    final, scale = apply_individual(
        ind, base_amounts, scale_materials_mask, efficiency_materials_mask
    )
    penalty = _scale_eff_penalties(
        scale, ind[1:], max_scale_deviation, max_efficiency_deviation
    )
    return (_cost(final, costs) + penalty,)


def evaluate_single_impact_constrained(
    ind,
    matrix,
    colname,
    cols,
    base_amounts,
    baseline_trees,
    scale_materials_mask,
    efficiency_materials_mask,
    max_scale_deviation,
    max_efficiency_deviation,
):
    final, scale = apply_individual(
        ind, base_amounts, scale_materials_mask, efficiency_materials_mask
    )
    penalty = _scale_eff_penalties(
        scale, ind[1:], max_scale_deviation, max_efficiency_deviation
    )
    try:
        idx = list(cols).index(colname)
        impact = float(np.dot(final, np.asarray(matrix, dtype=float)[:, idx].flatten()[: len(final)]))
    except (ValueError, IndexError):
        impact = 0.0
    return (impact + penalty,)


def _reset_creator(kind: str) -> None:
    for name in ("FitnessMin", "Individual"):
        if hasattr(creator, name):
            delattr(creator, name)
    if kind == "nsga":
        creator.create("FitnessMin", base.Fitness, weights=(-1.0, -1.0))
    else:
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    creator.create("Individual", list, fitness=creator.FitnessMin)


def _make_individual_factory(n_eff: int, max_scale_dev: float, max_eff_dev: float):
    def create_individual():
        ind = [random.uniform(1 - max_scale_dev, 1 + max_scale_dev)]
        for _ in range(int(n_eff)):
            ind.append(random.uniform(1 - max_eff_dev, 1 + max_eff_dev))
        return ind

    return create_individual


def _bounded_mutate_factory(max_scale_dev: float, max_eff_dev: float):
    def bounded_mutate(ind, mu=0.0, sigma=0.05, indpb=0.2):
        mutated = list(ind)
        for i in range(len(mutated)):
            if random.random() < indpb:
                mutated[i] += random.gauss(mu, sigma)
                if i == 0:
                    mutated[i] = float(np.clip(mutated[i], 1 - max_scale_dev, 1 + max_scale_dev))
                else:
                    mutated[i] = float(np.clip(mutated[i], 1 - max_eff_dev, 1 + max_eff_dev))
        return (mutated,)

    return bounded_mutate


def run_nsga2_constrained(
    popsize,
    ngen,
    cxpb,
    mutpb,
    costs,
    matrix,
    impact_cols,
    base_amounts,
    baseline_trees,
    scale_mask,
    efficiency_mask,
    max_scale_dev,
    max_eff_dev,
    eval_func: Optional[Callable] = None,
    seed: Optional[int] = None,
    **eval_kwargs,
):
    """NSGA-II. Returns the first non-dominated front (list of Individuals)."""
    set_seed(seed)
    _reset_creator("nsga")
    n_eff = int(np.sum(np.asarray(efficiency_mask, dtype=bool)))
    toolbox = base.Toolbox()
    toolbox.register(
        "individual",
        tools.initIterate,
        creator.Individual,
        _make_individual_factory(n_eff, max_scale_dev, max_eff_dev),
    )
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    if eval_func is None:
        eval_func = evaluate_cost_gwp_constrained
    toolbox.register(
        "evaluate",
        eval_func,
        costs=costs,
        impact_matrix=matrix,
        impact_cols=impact_cols,
        base_amounts=base_amounts,
        baseline_trees=baseline_trees,
        scale_materials_mask=scale_mask,
        efficiency_materials_mask=efficiency_mask,
        max_scale_deviation=max_scale_dev,
        max_efficiency_deviation=max_eff_dev,
        **eval_kwargs,
    )
    toolbox.register("mate", tools.cxBlend, alpha=0.3)
    toolbox.register("mutate", _bounded_mutate_factory(max_scale_dev, max_eff_dev))
    toolbox.register("select", tools.selNSGA2)

    pop = toolbox.population(n=popsize)
    for ind in pop:
        fit = toolbox.evaluate(ind)
        if not isinstance(fit, tuple) or len(fit) != 2:
            raise RuntimeError(f"NSGA evaluate must return a 2-tuple, got {fit!r}")
        ind.fitness.values = fit

    for _gen in range(ngen):
        offspring = toolbox.select(pop, popsize)
        offspring = [creator.Individual(list(ind)) for ind in offspring]
        for i in range(1, len(offspring), 2):
            if random.random() < cxpb:
                child1, child2 = toolbox.mate(offspring[i - 1], offspring[i])
                offspring[i - 1] = creator.Individual(child1)
                offspring[i] = creator.Individual(child2)
        for i in range(len(offspring)):
            if random.random() < mutpb:
                mutated, = toolbox.mutate(offspring[i])
                offspring[i] = creator.Individual(mutated)
        for ind in offspring:
            ind.fitness.values = toolbox.evaluate(ind)
        pop = toolbox.select(pop + offspring, popsize)

    return tools.sortNondominated(pop, k=len(pop), first_front_only=True)[0]


def run_single_constrained(
    obj_func,
    popsize,
    ngen,
    cxpb,
    mutpb,
    base_amounts,
    baseline_trees,
    scale_mask,
    efficiency_mask,
    max_scale_dev,
    max_eff_dev,
    *args,
    seed: Optional[int] = None,
    **kwargs,
):
    """Single-objective GA. Returns the Hall-of-Fame individual."""
    set_seed(seed)
    _reset_creator("single")
    n_eff = int(np.sum(np.asarray(efficiency_mask, dtype=bool)))
    toolbox = base.Toolbox()
    toolbox.register(
        "individual",
        tools.initIterate,
        creator.Individual,
        _make_individual_factory(n_eff, max_scale_dev, max_eff_dev),
    )
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register(
        "evaluate",
        obj_func,
        *args,
        base_amounts=base_amounts,
        baseline_trees=baseline_trees,
        scale_materials_mask=scale_mask,
        efficiency_materials_mask=efficiency_mask,
        max_scale_deviation=max_scale_dev,
        max_efficiency_deviation=max_eff_dev,
        **kwargs,
    )
    toolbox.register("mate", tools.cxBlend, alpha=0.3)
    toolbox.register("mutate", _bounded_mutate_factory(max_scale_dev, max_eff_dev))
    toolbox.register("select", tools.selTournament, tournsize=3)

    def _safe_eval(ind):
        try:
            fit = toolbox.evaluate(ind)
            if not isinstance(fit, tuple):
                fit = (fit,)
            if any(not np.isfinite(v) for v in fit):
                return (1e10,)
            return fit
        except Exception:
            return (1e10,)

    pop = toolbox.population(n=popsize)
    for ind in pop:
        ind.fitness.values = _safe_eval(ind)
    hof = tools.HallOfFame(1)

    for _gen in range(ngen):
        offspring = toolbox.select(pop, popsize)
        offspring = [creator.Individual(list(ind)) for ind in offspring]
        for i in range(1, len(offspring), 2):
            if random.random() < cxpb:
                child1, child2 = toolbox.mate(offspring[i - 1], offspring[i])
                offspring[i - 1] = creator.Individual(child1)
                offspring[i] = creator.Individual(child2)
        for i in range(len(offspring)):
            if random.random() < mutpb:
                mutated, = toolbox.mutate(offspring[i])
                offspring[i] = creator.Individual(mutated)
        for ind in offspring:
            ind.fitness.values = _safe_eval(ind)
        pop[:] = offspring
        hof.update(pop)

    return hof[0]
