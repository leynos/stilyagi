"""Sentence model placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class Sentence:
    """Placeholder sentence model for the package skeleton.

    Parameters
    ----------
    text:
        Sentence text preserved for future NLP-backed slices.
    """

    text: str
