"""Execution-planning placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Placeholder execution plan for the engine boundary.

    Parameters
    ----------
    syntax:
        Source syntax handled by the future execution plan.
    """

    syntax: str
