"""Execution-planning placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class ExecutionPlan:
    """Placeholder execution plan for the engine boundary.

    Parameters
    ----------
    syntax:
        Source syntax handled by the future execution plan.
    """

    syntax: str
