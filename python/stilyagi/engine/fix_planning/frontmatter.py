"""Recognize and protect source-backed YAML frontmatter during fixes."""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

from stilyagi.engine import ir_view
from stilyagi.engine.ir_mapping import is_sequence
from stilyagi.fixes import TextEdit

if typ.TYPE_CHECKING:
    from stilyagi import model


@dc.dataclass(frozen=True, slots=True)
class YamlFrontmatter:
    r"""The source span and byte-faithful closing-line prefix of YAML metadata.

    A recognized prefix is one the document's own IR still describes: the span
    is the region's claimed source range and ``prefix_bytes`` is what the
    source actually holds across it. Comparing those bytes before and after a
    planned splice is what proves a repair left the metadata alone.

    The ``None`` triple is the third state, and it is deliberately not the
    same as absence. It means the file *has* frontmatter the guard cannot
    verify -- several candidate regions, a region whose span is unusable, or
    region text that disagrees with the bytes it claims. Recognition cannot
    prove the prefix is intact, so every edit in the file is refused rather
    than planned against metadata nobody can vouch for. Only ``None`` for the
    whole value means the file carries no frontmatter and needs no guard.

    Attributes
    ----------
    span:
        The region's byte range in the source, excluding any closing line
        ending, or ``None`` when the region cannot be verified.
    protected_end:
        The offset just past one closing CRLF, LF, or CR ending -- when one is
        present -- which is the end of the prefix an edit must not touch, or
        ``None`` when unverified.
    prefix_bytes:
        The source bytes from ``span.byte_start`` to ``protected_end``, kept
        for the before-and-after comparison, or ``None`` when unverified.

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> source = "---\ntitle: Notes\n---\n\nBody\n"
    >>> frontmatter = yaml_frontmatter(
    ...     engine.extract_document(source, model.Syntax.MARKDOWN),
    ...     source.encode(),
    ... )
    >>> frontmatter.prefix_bytes
    b'---\ntitle: Notes\n---\n'
    """

    span: ir_view.SourceSpan | None
    protected_end: int | None
    prefix_bytes: bytes | None


def yaml_frontmatter(
    document: model.Document,
    source_bytes: bytes,
) -> YamlFrontmatter | None:
    r"""Return the YAML frontmatter source boundary, or ``None`` when absent.

    Parameters
    ----------
    document:
        The extracted document whose canonical IR is inspected for a
        frontmatter region.
    source_bytes:
        The exact bytes the document was extracted from. The region's claimed
        span is verified against them rather than trusted.

    Returns
    -------
    YamlFrontmatter | None
        The recognized prefix, the unverifiable triple
        ``YamlFrontmatter(None, None, None)`` when a frontmatter region exists
        but cannot be confirmed, or ``None`` when the document carries no
        frontmatter at all.

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> yaml_frontmatter(
    ...     engine.extract_document("# Title\n", model.Syntax.MARKDOWN),
    ...     b"# Title\n",
    ... ) is None
    True
    """
    regions = _yaml_frontmatter_regions(document)
    if not regions:
        return None
    if len(regions) != 1:
        return YamlFrontmatter(None, None, None)

    source_span = _verified_region_span(regions[0], source_bytes)
    if source_span is None:
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
    r"""Return whether an edit is invalid or overlaps a protected prefix.

    Overlap is judged against the whole protected prefix, closing line ending
    included, because a rule that consumed that ending would join the metadata
    to the body it precedes. An insertion overlaps when its zero-width position
    lies inside the half-open prefix; a replacement or removal when its range
    intersects it. A zero-width position exactly at ``protected_end`` lies
    outside that half-open range and does not overlap, which is why
    :func:`is_frontmatter_boundary_insertion` exists to suspend the bound there
    instead of relying on this test.

    Parameters
    ----------
    edit:
        The candidate edit. Any value outside the :class:`TextEdit` contract is
        treated as conflicting, so a rule that hands back a look-alike cannot
        slip past the guard.
    frontmatter:
        The recognition result for this document and source, or ``None`` when
        the document carries no frontmatter.

    Returns
    -------
    bool
        ``True`` when the edit must be refused: it is not a ``TextEdit``,
        frontmatter is present but unverifiable, or the edit overlaps the
        protected prefix. ``False`` when there is no frontmatter to protect or
        the edit lies wholly beyond it.

    Examples
    --------
    >>> from stilyagi import engine, model
    >>> from stilyagi.fixes import TextEdit
    >>> source = "---\ntitle: Notes\n---\n\nBody\n"
    >>> frontmatter = yaml_frontmatter(
    ...     engine.extract_document(source, model.Syntax.MARKDOWN),
    ...     source.encode(),
    ... )
    >>> edit_conflicts_with_frontmatter(TextEdit(22, 26, "Text"), frontmatter)
    False
    >>> edit_conflicts_with_frontmatter(TextEdit(0, 3, "+++"), frontmatter)
    True
    """
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
    r"""Return whether an insertion sits just after the protected prefix.

    A zero-width edit at ``protected_end`` touches the prefix at neither byte,
    so the overlap test answers ``False`` for it; it is nevertheless the one
    place the admissibility bound has to be suspended. The prefix ends with its
    closing line ending, so the position is the start of the body, and text
    inserted there precedes the body rather than entering the metadata.

    Parameters
    ----------
    edit:
        The candidate edit, which must be zero-width to qualify.
    frontmatter:
        The recognition result for this document and source, or ``None``.

    Returns
    -------
    bool
        ``True`` only for a zero-width edit at exactly ``protected_end`` of a
        verifiable prefix. An absent or unverifiable frontmatter has no such
        position and answers ``False``.

    Examples
    --------
    >>> from stilyagi.engine import ir_view
    >>> from stilyagi.fixes import TextEdit
    >>> block = b"---\ntitle: x\n---\n"
    >>> len(block)
    17
    >>> known = YamlFrontmatter(ir_view.SourceSpan(0, 16), 17, block)
    >>> is_frontmatter_boundary_insertion(TextEdit(17, 17, "!"), known)
    True
    >>> is_frontmatter_boundary_insertion(TextEdit(16, 16, "!"), known)
    False
    """
    return (
        frontmatter is not None
        and frontmatter.protected_end is not None
        and edit.byte_start == edit.byte_end == frontmatter.protected_end
    )


def frontmatter_is_unchanged(
    before: YamlFrontmatter | None,
    after: YamlFrontmatter | None,
) -> bool:
    """Compare recognized YAML frontmatter bytes before and after a splice.

    The comparison is over bytes rather than over recognition alone, because a
    splice can leave the region recognizable while changing what the prefix
    says. An unverifiable side has no bytes to compare and therefore counts as
    changed: a repair is only allowed to proceed when both sides can be shown
    to hold the same prefix.

    Parameters
    ----------
    before:
        Recognition of the source the plan was made from.
    after:
        Recognition of the planned replacement, re-extracted from its text.

    Returns
    -------
    bool
        ``True`` when neither side has frontmatter, or when both have a
        verifiable prefix holding identical bytes. ``False`` when one side has
        frontmatter and the other does not, or when either side is
        unverifiable.

    Examples
    --------
    >>> frontmatter_is_unchanged(None, None)
    True
    >>> frontmatter_is_unchanged(None, YamlFrontmatter(None, None, None))
    False
    """
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
    if not is_sequence(raw_regions):
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
    if not is_sequence(raw_segments):
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


def _verified_region_span(
    region: cabc.Mapping[str, object],
    source_bytes: bytes,
) -> ir_view.SourceSpan | None:
    """Return the region's first claimed source span, once its text is verified.

    The span and the text that has to back it are read from the same segment,
    so one segment cannot supply the offsets while another supplies the text.
    Both failures -- an unusable span and text that disagrees with the bytes it
    claims -- refuse the whole region rather than searching past it for a
    segment that happens to agree. The region asserts that it describes the
    prefix; a segment that contradicts the source means the recognition is
    stale, and a later segment agreeing would not make the first one true.

    Returns
    -------
    ir_view.SourceSpan | None
        The first segment's span when its text matches the bytes it claims,
        or ``None`` when the region offers no usable first segment or that
        segment disagrees with the source.
    """
    first = next(iter(_source_segments(region)), None)
    if first is None:
        return None
    segment, source = first
    span = _source_span(source.get("byte_start"), source.get("byte_end"))
    if span is None:
        return None
    return span if _source_text_matches(segment, span, source_bytes) else None


def _source_text_matches(
    segment: cabc.Mapping[str, object],
    span: ir_view.SourceSpan,
    source_bytes: bytes,
) -> bool:
    """Decode one verified source range and compare its segment text."""
    if span.byte_end > len(source_bytes):
        return False
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
