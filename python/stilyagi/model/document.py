"""Document model placeholders for Stilyagi."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from .region import Region


@dc.dataclass(frozen=True)
class Document:
    """Placeholder document model for the package skeleton.

    Parameters
    ----------
    syntax:
        Source syntax represented by the document.
    regions:
        Flattened future prose regions contained by the document.
    """

    syntax: str
    regions: tuple[Region, ...] = ()
