"""Fix-planning placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
class FixPlan:
    """Placeholder fix plan for the package skeleton.

    Parameters
    ----------
    applicability:
        Future fix applicability classification.
    """

    applicability: str
