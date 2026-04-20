"""Region model placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
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
