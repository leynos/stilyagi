"""Execution-runner placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from .planner import ExecutionPlan


@dc.dataclass(frozen=True)
class EngineRunner:
    """Placeholder engine runner for the package skeleton.

    Parameters
    ----------
    execution_plan:
        Planned work for the future engine slice.
    """

    execution_plan: ExecutionPlan
