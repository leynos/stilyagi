"""Token model placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class Token:
    """Placeholder token model for the package skeleton.

    Parameters
    ----------
    text:
        Token text preserved for future NLP-backed slices.
    """

    text: str
