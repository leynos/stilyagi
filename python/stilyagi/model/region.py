"""Region model placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class Region:
    """Placeholder region model for the package skeleton.

    Parameters
    ----------
    kind:
        Future region kind name.
    text:
        Region text carried into the future rule engine.
    """

    kind: str
    text: str
