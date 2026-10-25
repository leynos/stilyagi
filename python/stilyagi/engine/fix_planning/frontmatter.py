"""Recognize and protect source-backed YAML frontmatter during fixes."""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

from stilyagi.engine import ir_view
from stilyagi.fixes import TextEdit

if typ.TYPE_CHECKING:
    from stilyagi import model


@dc.dataclass(frozen=True, slots=True)
class YamlFrontmatter:
    """The source span and byte-faithful closing-line prefix of YAML metadata."""

    span: ir_view.SourceSpan | None
    protected_end: int | None
    prefix_bytes: bytes | None


def yaml_frontmatter(
    document: model.Document,
    source_bytes: bytes,
) -> YamlFrontmatter | None:
    """Return the YAML frontmatter source boundary, or ``None`` when absent."""
    regions = _yaml_frontmatter_regions(document)
    if not regions:
        return None
    if len(regions) != 1:
        return YamlFrontmatter(None, None, None)

    source_span = _region_source_span(regions[0])
    if source_span is None or not _matches_region_text(
        regions[0], source_span, source_bytes
    ):
        return YamlFrontmatter(None, None, None)
    protected_end = _closing_line_end(source_bytes, source_span.byte_end)
    return YamlFrontmatter(
        source_span,
        protected_end,
        source_bytes[source_span.byte_start : protected_end],
    )


def edit_conflicts_with_frontmatter(
    edit: TextEdit,
    frontmatter: YamlFrontmatter | None,
) -> bool:
    """Return whether an edit is invalid or overlaps a protected prefix."""
    if not isinstance(edit, TextEdit):
        return True
    if frontmatter is None:
        return False
    if frontmatter.span is None or frontmatter.protected_end is None:
        return True

    start = frontmatter.span.byte_start
    if edit.byte_start == edit.byte_end:
        return start <= edit.byte_start < frontmatter.protected_end
    return edit.byte_start < frontmatter.protected_end and edit.byte_end > start


def is_frontmatter_boundary_insertion(
    edit: TextEdit,
    frontmatter: YamlFrontmatter | None,
) -> bool:
    """Return whether an insertion sits just after the protected prefix."""
    return (
        frontmatter is not None
        and frontmatter.protected_end is not None
        and edit.byte_start == edit.byte_end == frontmatter.protected_end
    )


def frontmatter_is_unchanged(
    before: YamlFrontmatter | None,
    after: YamlFrontmatter | None,
) -> bool:
    """Compare recognized YAML frontmatter bytes before and after a splice."""
    if before is None or after is None:
        return before is None and after is None
    return before.prefix_bytes is not None and before.prefix_bytes == after.prefix_bytes


def _yaml_frontmatter_regions(
    document: model.Document,
) -> tuple[cabc.Mapping[str, object], ...]:
    """Return YAML frontmatter regions from a well-formed IR envelope."""
    if document.ir is None:
        return ()
    raw_regions = document.ir.get("regions")
    if not ir_view._is_sequence(raw_regions):
        return ()
    return tuple(
        region
        for raw_region in raw_regions
        if (region := _yaml_frontmatter_region(raw_region)) is not None
    )


def _yaml_frontmatter_region(
    raw_region: object,
) -> cabc.Mapping[str, object] | None:
    """Return a region mapping only when it identifies YAML frontmatter."""
    region = _as_mapping(raw_region)
    if region is None:
        return None
    if region.get("kind") != "frontmatter":
        return None
    if not _yaml_attributes(region.get("attrs")):
        return None
    return region


def _yaml_attributes(value: object) -> bool:
    """Return whether region attributes identify YAML frontmatter."""
    attributes = _as_mapping(value)
    return attributes is not None and attributes.get("format") == "yaml"


def _source_segments(
    region: cabc.Mapping[str, object],
) -> cabc.Iterator[tuple[cabc.Mapping[str, object], cabc.Mapping[str, object]]]:
    """Yield segment and source mappings with valid shapes."""
    raw_segments = region.get("segments")
    if not ir_view._is_sequence(raw_segments):
        return
    for raw_segment in raw_segments:
        source_segment = _source_segment(raw_segment)
        if source_segment is not None:
            yield source_segment


def _source_segment(
    raw_segment: object,
) -> tuple[cabc.Mapping[str, object], cabc.Mapping[str, object]] | None:
    """Narrow an IR segment to a valid segment and source mapping pair."""
    segment = _as_mapping(raw_segment)
    if segment is None:
        return None
    source = _as_mapping(segment.get("source"))
    if source is None:
        return None
    return segment, source


def _region_source_span(
    region: cabc.Mapping[str, object],
) -> ir_view.SourceSpan | None:
    """Return the first valid source span carried by a frontmatter region."""
    for _, source in _source_segments(region):
        start = source.get("byte_start")
        end = source.get("byte_end")
        return _source_span(start, end)
    return None


def _matches_region_text(
    region: cabc.Mapping[str, object],
    span: ir_view.SourceSpan,
    source_bytes: bytes,
) -> bool:
    """Ensure the source-backed segment still describes its claimed bytes."""
    if span.byte_end > len(source_bytes):
        return False
    for segment, source in _source_segments(region):
        if source.get("byte_start") != span.byte_start:
            continue
        if source.get("byte_end") != span.byte_end:
            continue
        return _source_text_matches(segment, span, source_bytes)
    return False


def _source_text_matches(
    segment: cabc.Mapping[str, object],
    span: ir_view.SourceSpan,
    source_bytes: bytes,
) -> bool:
    """Decode one verified source range and compare its segment text."""
    try:
        return source_bytes[span.byte_start : span.byte_end].decode() == segment.get(
            "text"
        )
    except UnicodeDecodeError:
        return False


def _closing_line_end(source_bytes: bytes, offset: int) -> int:
    """Include one CRLF, LF, or CR ending after the closing fence."""
    if source_bytes[offset : offset + 2] == b"\r\n":
        return offset + 2
    if source_bytes[offset : offset + 1] in {b"\n", b"\r"}:
        return offset + 1
    return offset


def _source_span(start: object, end: object) -> ir_view.SourceSpan | None:
    """Build a source span when both byte offsets form an ordered range."""
    if type(start) is not int or type(end) is not int:
        return None
    if start < 0 or start > end:
        return None
    return ir_view.SourceSpan(start, end)


def _as_mapping(value: object) -> cabc.Mapping[str, object] | None:
    """Narrow an untrusted IR value to a string-keyed mapping."""
    if not isinstance(value, cabc.Mapping):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return typ.cast("cabc.Mapping[str, object]", value)
