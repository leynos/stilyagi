"""Public engine commands that wrap lower-level adapters."""

import typing as typ

from . import extraction as _extraction

if typ.TYPE_CHECKING:
    from stilyagi import model


def extract_document(source: str, syntax: model.Syntax) -> model.Document:
    """Extract a document and report user-facing IR compatibility warnings."""
    document = _extraction.extract_document(source, syntax)
    _extraction.warn_unknown_ir_region_kinds(
        document.ir,
        operation="stilyagi.engine.extract_document",
    )
    return document
