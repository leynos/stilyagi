"""Public engine commands for document extraction.

This module is the supported command surface for callers that want to extract
structured Stilyagi documents. It delegates parsing to the lower-level
extraction adapter, then applies user-facing compatibility reporting for the
canonical IR payload returned by the embedded Rust bridge.

Example
-------
>>> from stilyagi import engine, model
>>> document = engine.extract_document("# Title", model.Syntax.MARKDOWN)
>>> document.regions[0].kind
'heading'
"""

import typing as typ

from . import extraction as _extraction

if typ.TYPE_CHECKING:
    from stilyagi import model


def extract_document(source: str, syntax: model.Syntax) -> model.Document:
    """Extract a source document through the public engine boundary.

    Parameters
    ----------
    source
        Source text to extract. For Markdown, non-blank text may produce typed
        regions such as headings, paragraphs, tables, lists, blockquotes,
        frontmatter, image alt text, and link titles.
    syntax
        Syntax identifier for the source text. The first implemented extractor
        supports ``model.Syntax.MARKDOWN``.

    Returns
    -------
    model.Document
        Extracted document containing the stable Python region view and, when
        supplied by the Rust bridge, the canonical ``Document.ir`` payload.

    Warnings
    --------
    Unknown canonical IR region kinds are preserved in ``Document.ir`` and
    reported through the ``stilyagi.engine.extraction`` logger. This keeps the
    lower-level adapter read-only while making compatibility drift visible at
    the supported public command boundary.
    """
    document = _extraction.extract_document(source, syntax)
    _extraction.warn_unknown_ir_region_kinds(
        document.ir,
        operation="stilyagi.engine.extract_document",
    )
    return document
