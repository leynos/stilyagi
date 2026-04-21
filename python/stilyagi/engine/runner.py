"""Engine-runner boundary placeholders for Stilyagi.

This module defines the minimal runner-side contract exposed by the
``stilyagi.engine`` package during the mixed-package skeleton phase. It gives
callers a stable import location for the future execution entrypoint while the
real planning and orchestration behaviour is still deferred to later roadmap
slices.

The public API boundary in this module is the :class:`EngineRunner` dataclass.
Callers should construct it with an :class:`~stilyagi.engine.planner.ExecutionPlan`
instance and treat it as the runner-side container for planned engine work.
No execution functions live here yet, so consumers should import the class but
should not expect runnable engine behaviour from this module in the current
slice.

Examples
--------
Import the runner boundary from the public engine package and keep hold of the
planned work it wraps::

    >>> from stilyagi.engine import EngineRunner, ExecutionPlan
    >>> plan = ExecutionPlan(syntax="markdown")
    >>> runner = EngineRunner(execution_plan=plan)
    >>> runner.execution_plan is plan
    True
"""

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

    execution_plan: ExecutionPlan
