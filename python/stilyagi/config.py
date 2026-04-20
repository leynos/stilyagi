"""Configuration boundary placeholders for Stilyagi."""

import dataclasses as dc
import pathlib


class InvalidCacheDirError(ValueError):
    """Raised when the cache-directory setting is blank."""


@dc.dataclass(frozen=True, slots=True)
class StilyagiConfig:
    """Minimal configuration placeholder for the package skeleton.

    Parameters
    ----------
    cache_dir:
        Repository-relative cache directory for future engine slices.
    """

    cache_dir: pathlib.Path = pathlib.Path(".stilyagi_cache")

    def __post_init__(self) -> None:
        """Reject unusable empty cache-directory values."""
        if not str(self.cache_dir).strip():
            raise InvalidCacheDirError
