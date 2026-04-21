"""Execution-runner placeholders for Stilyagi."""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from .planner import ExecutionPlan


@dc.dataclass(frozen=True, slots=True)
class EngineRunner:
    """Placeholder engine runner for the package skeleton.

    Parameters
    ----------
    execution_plan:
        Planned work for the future engine slice.
    """

    execution_plan: "ExecutionPlan"  # noqa: UP037
