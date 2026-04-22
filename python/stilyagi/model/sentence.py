"""Sentence model placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
class Sentence:
    """Placeholder sentence model for the package skeleton.

    Parameters
    ----------
    text:
        Sentence text preserved for future NLP-backed slices.
    """

    text: str
