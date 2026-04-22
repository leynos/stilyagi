"""Token model placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
class Token:
    """Placeholder token model for the package skeleton.

    Parameters
    ----------
    text:
        Token text preserved for future NLP-backed slices.
    """

    text: str
