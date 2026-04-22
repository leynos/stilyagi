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

def extract_document(source: str, syntax: str) -> ExtractDocumentPayload: ...
def hello() -> str: ...
def supported_syntaxes() -> tuple[str, ...]: ...
