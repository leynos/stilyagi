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
from .hydration import hydrate_canonical_ir

if typ.TYPE_CHECKING:
    from stilyagi import model


def extract_document(
    source: str,
    syntax: model.Syntax,
    *,
    source_path: str | None = None,
) -> model.Document:
    """Extract a source document through the public engine boundary.

    Parameters
    ----------
    source
        Source text to extract. For Markdown, non-blank text may produce typed
        regions such as headings, paragraphs, tables, lists, blockquotes,
        frontmatter, image alt text, and link titles.
    syntax
        Syntax identifier for the source text. Built-in extraction supports
        Markdown, Python docstrings, and Rust documentation comments.
    source_path
        Optional reported path to preserve in canonical IR metadata.

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

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> document = engine.extract_document(
    ...     "# Title", model.Syntax.MARKDOWN, source_path="README.md"
    ... )
    >>> document.ir["document"]["path"]
    'README.md'
    """
    document = _extraction.extract_document(
        source,
        syntax,
        source_path=source_path,
    )
    _extraction.warn_unknown_ir_region_kinds(
        document.ir,
        operation="stilyagi.engine.extract_document",
    )
    return document


def extract_document_result(
    source: str,
    syntax: model.Syntax,
    *,
    source_path: str | None = None,
) -> _extraction.ExtractionResult:
    r"""Extract a document while retaining Rust's canonical JSON string.

    Parameters
    ----------
    source
        Source text to extract.
    syntax
        Syntax identifier for the source text.
    source_path
        Optional reported path to preserve in canonical IR metadata.

    Returns
    -------
    stilyagi.engine.extraction.ExtractionResult
        The typed document and the canonical JSON string emitted by Rust.

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> result = engine.extract_document_result(
    ...     "# Title", model.Syntax.MARKDOWN, source_path="README.md"
    ... )
    >>> result.document.ir["document"]["path"]
    'README.md'
    >>> result.canonical_json.endswith("\n")
    True
    """
    result = _extraction.extract_document_result(
        source,
        syntax,
        source_path=source_path,
    )
    _extraction.warn_unknown_ir_region_kinds(
        result.document.ir,
        operation="stilyagi.engine.extract_document",
    )
    return result


def hydrate_ir_json(canonical_json: str) -> _extraction.ExtractionResult:
    """Hydrate a typed document through Rust's canonical IR schema.

    Parameters
    ----------
    canonical_json
        Complete canonical IR JSON previously emitted by the Rust extractor.

    Returns
    -------
    stilyagi.engine.extraction.ExtractionResult
        The typed document restored by Rust plus the original JSON string.

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> extracted = engine.extract_document_result("# Title", model.Syntax.MARKDOWN)
    >>> engine.hydrate_ir_json(extracted.canonical_json).document == extracted.document
    True
    """
    result = hydrate_canonical_ir(canonical_json)
    _extraction.warn_unknown_ir_region_kinds(
        result.document.ir,
        operation="stilyagi.engine.hydrate_ir_json",
    )
    return result
