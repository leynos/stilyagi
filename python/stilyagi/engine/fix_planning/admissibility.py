"""Classify rule edits against byte-faithful source provenance."""

import dataclasses as dc
import typing as typ

from stilyagi.engine import ir_view

from .frontmatter import (
    YamlFrontmatter,
    edit_conflicts_with_frontmatter,
    is_frontmatter_boundary_insertion,
    yaml_frontmatter,
)

if typ.TYPE_CHECKING:
    from stilyagi import model
    from stilyagi.fixes import TextEdit


_UTF8_CONTINUATION_MASK = 0b1100_0000
_UTF8_CONTINUATION_PREFIX = 0b1000_0000


@dc.dataclass(frozen=True, slots=True)
class EditRejection:
    """One refused edit and the rule code responsible for it."""

    identifier: str
    rule_code: str
    detail: str


def classify_edit(
    edit: TextEdit,
    source_bytes: bytes,
    document: model.Document,
    rule_code: str,
) -> EditRejection | None:
    """Return a rejection when an edit is not source-backed and UTF-8 aligned."""
    span = ir_view.SourceSpan(edit.byte_start, edit.byte_end)
    rejection = _span_rejection(span, source_bytes, rule_code)
    if rejection is not None:
        return rejection
    frontmatter = yaml_frontmatter(document, source_bytes)
    rejection = _frontmatter_rejection(edit, frontmatter, rule_code)
    if rejection is not None:
        return rejection
    if is_frontmatter_boundary_insertion(edit, frontmatter):
        return None
    return _source_backing_rejection(span, source_bytes, document, rule_code)


def _span_rejection(
    span: ir_view.SourceSpan,
    source_bytes: bytes,
    rule_code: str,
) -> EditRejection | None:
    """Reject spans outside the input or between UTF-8 continuation bytes."""
    if not _is_bounded(span, source_bytes):
        return EditRejection(
            "fix-error/invalid-span", rule_code, "span is out of bounds"
        )
    if not _is_utf8_aligned(span, source_bytes):
        return EditRejection(
            "fix-error/non-utf8-boundary", rule_code, "span cuts UTF-8"
        )
    return None


def _frontmatter_rejection(
    edit: TextEdit,
    frontmatter: YamlFrontmatter | None,
    rule_code: str,
) -> EditRejection | None:
    """Reject edits that overlap or cannot verify YAML metadata bytes."""
    if edit_conflicts_with_frontmatter(edit, frontmatter):
        return EditRejection(
            "fix-error/frontmatter-protected",
            rule_code,
            "edit overlaps or cannot verify YAML frontmatter bytes",
        )
    return None


def _source_backing_rejection(
    span: ir_view.SourceSpan,
    source_bytes: bytes,
    document: model.Document,
    rule_code: str,
) -> EditRejection | None:
    """Reject spans not supported by a matching source segment."""
    if not _is_source_backed(span, document):
        return EditRejection(
            "fix-error/synthetic-span", rule_code, "span is not source-backed"
        )
    if not _segment_matches_source(span, source_bytes, document):
        return EditRejection(
            "fix-error/source-mismatch",
            rule_code,
            "IR segment text disagrees with source",
        )
    return None


def _is_bounded(span: ir_view.SourceSpan, source_bytes: bytes) -> bool:
    """Return whether a span is ordered and lies within source bytes."""
    return 0 <= span.byte_start <= span.byte_end <= len(source_bytes)


def _is_utf8_aligned(span: ir_view.SourceSpan, source_bytes: bytes) -> bool:
    """Return whether both span boundaries fall between UTF-8 code points."""
    return _is_utf8_boundary(source_bytes, span.byte_start) and _is_utf8_boundary(
        source_bytes, span.byte_end
    )


def _is_utf8_boundary(source_bytes: bytes, offset: int) -> bool:
    """Return whether one bounded offset is not a UTF-8 continuation byte."""
    return (
        offset == len(source_bytes)
        or source_bytes[offset] & _UTF8_CONTINUATION_MASK != _UTF8_CONTINUATION_PREFIX
    )


def _is_source_backed(span: ir_view.SourceSpan, document: model.Document) -> bool:
    """Return whether one merged source-backed span contains the edit."""
    return any(
        source_span.byte_start
        <= span.byte_start
        <= span.byte_end
        <= source_span.byte_end
        for source_span in ir_view.source_backed_spans(document)
    )


def _segment_matches_source(
    span: ir_view.SourceSpan,
    source_bytes: bytes,
    document: model.Document,
) -> bool:
    """Return whether the containing segment's claimed source bytes match its text."""
    segment = ir_view.segment_for_span(document, span)
    if segment is None or segment.span is None:
        return False
    if not _is_bounded(segment.span, source_bytes):
        return False
    if not _is_utf8_aligned(segment.span, source_bytes):
        return False
    try:
        segment_bytes = source_bytes[segment.span.byte_start : segment.span.byte_end]
        return segment_bytes.decode() == segment.text
    except UnicodeDecodeError:
        return False
