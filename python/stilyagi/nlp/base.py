"""Natural language processing provider protocols for Stilyagi."""

from __future__ import annotations

import typing as typ


class NlpProvider(typ.Protocol):
    """Protocol for future NLP providers."""

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
