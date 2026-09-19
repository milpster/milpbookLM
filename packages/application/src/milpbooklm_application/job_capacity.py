"""
Capacity policy loading (ch15 "Fairness", FND-05).

Administrator-configured per-class concurrency over the baseline policy via
``MILPBOOKLM_CAPACITY_<CLASS>`` environment values (e.g.
``MILPBOOKLM_CAPACITY_MEDIA=0`` parks every media job durably as
``waiting_capacity``). The loader takes the environment mapping - it does not
read ``os`` - so the application layer stays framework-free.
"""

from __future__ import annotations

from collections.abc import Mapping

from milpbooklm_domain.job_capacity import (
    DEFAULT_CAPACITY_POLICY,
    CapacityClass,
    CapacityPolicy,
    ClassBudget,
)

ENV_PREFIX = "MILPBOOKLM_CAPACITY_"


def load_capacity_policy(env: Mapping[str, str]) -> CapacityPolicy:
    """Apply the environment's per-class concurrency overrides to the baseline policy."""
    budgets: dict[CapacityClass, ClassBudget] = {}
    for job_class, budget in DEFAULT_CAPACITY_POLICY.budgets.items():
        raw = env.get(ENV_PREFIX + job_class.value.upper(), "").strip()
        if raw:
            budgets[job_class] = ClassBudget(int(raw), budget.max_concurrent_per_user)
        else:
            budgets[job_class] = budget
    return CapacityPolicy(budgets=budgets)
