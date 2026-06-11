"""Document model placeholders for Stilyagi."""

import dataclasses as dc
import enum
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .region import Region


class Syntax(enum.StrEnum):
    """Closed syntax vocabulary for the initial document skeleton."""

    MARKDOWN = "markdown"
    PYTHON_DOCSTRING = "python_docstring"
    RUST_DOC_COMMENT = "rust_doc_comment"


@dc.dataclass(frozen=True, slots=True)
class Document:
    """Placeholder document model for the package skeleton.

    Parameters
    ----------
    syntax:
        Source syntax represented by the document.
    regions:
        Flattened future prose regions contained by the document.
    ir:
        Full IR document envelope when the extractor provides one.
    """

    syntax: Syntax
    regions: tuple[Region, ...] = ()
    ir: cabc.Mapping[str, object] | None = None
