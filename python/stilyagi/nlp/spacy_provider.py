"""spaCy-provider placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class SpacyProviderConfig:
    """Placeholder configuration for the future spaCy provider.

    Parameters
    ----------
    model:
        spaCy model identifier for later NLP-backed slices.
    """

    model: str = "en-core-web-sm"
