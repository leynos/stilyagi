"""Diagnostics boundary placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc


@dc.dataclass(frozen=True)
class Diagnostic:
    """Minimal diagnostic placeholder for the package skeleton.

    Parameters
    ----------
    code:
        Stable identifier for the future diagnostic.
    message:
        Human-readable explanation of the future diagnostic.
    """

    code: str
    message: str
