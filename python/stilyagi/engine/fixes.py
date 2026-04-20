"""Fix-planning placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class FixPlan:
    """Placeholder fix plan for the package skeleton.

    Parameters
    ----------
    applicability:
        Future fix applicability classification.
    """

    applicability: str
