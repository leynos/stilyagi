"""Configuration boundary placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


class InvalidCacheDirError(ValueError):
    """Raised when the cache-directory setting is blank."""


@dc.dataclass(frozen=True)
class StilyagiConfig:
    """Minimal configuration placeholder for the package skeleton.

    Parameters
    ----------
    cache_dir:
        Repository-relative cache directory for future engine slices.
    """

    cache_dir: str = ".stilyagi_cache"

    def __post_init__(self) -> None:
        """Reject unusable empty cache-directory values."""
        if not self.cache_dir.strip():
            raise InvalidCacheDirError
