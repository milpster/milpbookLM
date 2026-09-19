"""
Capacity-class budgets and basic fairness quotas (ch15 "Fairness", FND-05).

Five capacity classes separate interactive text, ingestion/indexing,
research/browser, execution and media work so one user or class cannot starve
the others. The baseline (D12 prototype scope) is a basic per-class
concurrency cap plus a per-user cap inside each class; weighted fair selection
and administrator-configured cost budgets are wave 2. Budgets are checked at
ENQUEUE (a job whose class is saturated is durably parked as
``waiting_capacity`` with a visible reason) and at DISPATCH (a worker claims
from a class only while its in-flight count is under the cap).
"""

from __future__ import annotations

from dataclasses import dataclass

from milpbooklm_domain.jobs import CapacityClass

__all__ = [
    "DEFAULT_CAPACITY_POLICY",
    "CapacityClass",  # re-exported: callers import the class from this module
    "CapacityPolicy",
    "ClassBudget",
    "capacity_saturated",
]


@dataclass(frozen=True, slots=True)
class ClassBudget:
    """Per-class concurrency limits: installation-wide and per-user caps."""

    max_concurrent: int
    max_concurrent_per_user: int


@dataclass(frozen=True, slots=True)
class CapacityPolicy:
    """
    The installation's capacity policy: one budget per capacity class.

    D12 prototype scope: basic per-class caps suffice; weighted fairness across
    installation/user/notebook and cost budgets are deferred to wave 2.
    """

    budgets: dict[CapacityClass, ClassBudget]

    def budget(self, job_class: CapacityClass) -> ClassBudget:
        """Return the budget for one class; unknown classes are a configuration error."""
        try:
            return self.budgets[job_class]
        except KeyError:
            raise ValueError(f"no capacity budget configured for class {job_class.value}") from None


# Baseline installation budgets (ch15: five separate capacity classes).
DEFAULT_CAPACITY_POLICY = CapacityPolicy(
    budgets={
        CapacityClass.INTERACTIVE_TEXT: ClassBudget(4, 2),
        CapacityClass.INGESTION_INDEXING: ClassBudget(2, 2),
        CapacityClass.RESEARCH_BROWSER: ClassBudget(2, 1),
        CapacityClass.EXECUTION: ClassBudget(2, 1),
        CapacityClass.MEDIA: ClassBudget(1, 1),
    }
)


def capacity_saturated(
    budget: ClassBudget, *, in_flight_class: int, in_flight_user: int
) -> bool:
    """
    Return True when the class has no dispatchable capacity left.

    Used at enqueue (to durably park the job as waiting_capacity) and at
    dispatch (to skip the class for this claim round).
    """
    return in_flight_class >= budget.max_concurrent or (
        in_flight_user >= budget.max_concurrent_per_user
    )
