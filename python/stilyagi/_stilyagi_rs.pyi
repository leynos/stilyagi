"""Typing stub for the package-scoped Rust extension."""

import typing as typ

class ExtractRegion(typ.TypedDict):
    """Bridge payload for one extracted prose region."""

    kind: str
    text: str

class ExtractDocumentPayload(typ.TypedDict):
    """Bridge payload for one extracted document."""

    syntax: str
    regions: list[ExtractRegion]
    ir_json: typ.NotRequired[str]

def extract_document(source: str, syntax: str) -> ExtractDocumentPayload:
    """Extract structured document data from *source* using *syntax*.

    Returns an ``ExtractDocumentPayload`` containing ``syntax``, ``regions``,
    and optional ``ir_json``.

    Raises ``ValueError`` when *syntax* is invalid, ``NotImplementedError``
    when it is recognised but unavailable, and ``TypeError`` for invalid
    argument types.
    """

def hello() -> str: ...
def supported_syntaxes() -> tuple[str, ...]: ...
