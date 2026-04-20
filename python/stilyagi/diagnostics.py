"""Diagnostics boundary placeholders for Stilyagi."""

import dataclasses as dc


@dc.dataclass(frozen=True, slots=True)
class NodeRef:
    """Placeholder node reference for the future rule runtime."""

    kind: str
    text: str


@dc.dataclass(frozen=True, slots=True)
class Fix:
    """Placeholder fix object for the future rule runtime."""

    description: str


@dc.dataclass(frozen=True, slots=True)
class Diagnostic:
    """Minimal diagnostic placeholder for the package skeleton.

    Parameters
    ----------
    code:
        Stable identifier for the future diagnostic.
    message:
        Human-readable explanation of the future diagnostic.
    span:
        Placeholder source node reference associated with the diagnostic.
    fix:
        Optional placeholder fix attached to the diagnostic.
    """

    code: str
    message: str
    span: NodeRef
    fix: Fix | None = None
