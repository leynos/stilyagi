"""Configuration boundary placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class StilyagiConfig:
    """Minimal configuration placeholder for the package skeleton.

    Parameters
    ----------
    cache_dir:
        Repository-relative cache directory for future engine slices.
    """

    cache_dir: str = ".stilyagi_cache"
