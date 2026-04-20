"""Renderer placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class RendererRegistry:
    """Placeholder renderer registry for the package skeleton.

    Parameters
    ----------
    default_format:
        Preferred output format for future diagnostics.
    """

    default_format: str = "text"
