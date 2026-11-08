"""Generated YAML-frontmatter documents for planning and guard properties.

The corpus strategies deliberately step around frontmatter: an edit that
crosses the protected prefix is refused by design, so drawing one there would
only measure the refusal. That leaves the guard's own invariant unexercised by
generated input, and the hand-written contracts in `test_fix_frontmatter.py`
and `test_frontmatter_cli.py` cover selected examples of it rather than a
range.

This module generates the document instead. A source is a frontmatter block,
one of the three line endings the guard treats as a closing ending, an optional
byte-order mark, and -- in the *terminated* family -- a two-paragraph body.

Both fence families are generated because the guard's two halves are not
load-bearing in the same places. When the closing fence is followed by a line
ending, ``protected_end`` is the start of the body and the per-edit overlap
test decides the boundary; when the fence ends the file instead,
``protected_end`` is the end of the source, the overlap test admits an
insertion there, and only the plan-level re-extraction and prefix comparison
refuses it. A set drawn from the terminated family alone can be made to pass
with that comparison stubbed out, so it would not measure the half it claims
to.

Every generated source is extracted and checked against three assumptions the
properties rely on: the frontmatter is recognized and verifiable, the protected
prefix excludes the mark, and -- for the terminated family -- at least one
source-backed span lies wholly after it. A case that violates one is discarded
rather than turned into an edit, so a property never asserts on an edit the
planner could not have accepted anyway.
"""

import dataclasses as dc
import functools

import hypothesis.strategies as st
from stilyagi import engine, model
from stilyagi.engine import ir_view
from stilyagi.engine.fix_planning.frontmatter import YamlFrontmatter, yaml_frontmatter
from stilyagi.engine.fix_planning.offset_view import OffsetView

_BOM_TEXT = "﻿"

#: YAML shapes the block generator may draw: a plain scalar, a quoted scalar
#: holding a colon, a comment above the first key, a flow sequence, a literal
#: block, and a non-ASCII scalar. Each is legal frontmatter the extractor
#: reports as one region, which the module-level probe in the tests re-checks.
_YAML_BLOCKS: tuple[tuple[str, ...], ...] = (
    ("title: Notes",),
    ("title: 'a: b'",),
    ("# leading comment", "title: Notes"),
    ("tags: [alpha, beta]",),
    ("description: |", "  first line", "  second line"),
    ("title: Café",),
)


@dc.dataclass(frozen=True, slots=True)
class FrontmatterCase:
    """One generated source and the offsets its extraction reports.

    Attributes
    ----------
    source_bytes:
        The complete source, including any byte-order mark.
    body:
        The bytes the IR offsets address, with the mark split off.
    document:
        The extraction of ``body`` decoded exactly as the reader decodes it.
    frontmatter:
        Recognition of ``document`` against ``body``. Always a verifiable
        prefix: cases whose recognition is absent or unverifiable are
        discarded by the caller.
    prefix_bytes:
        The recognized prefix, copied out of ``frontmatter`` so consumers get
        ``bytes`` rather than the recognizer's optional triple.
    protected_end:
        The offset just past the closing line ending, in the ``body`` view.
    body_span:
        One source-backed span wholly after ``protected_end``, or ``None`` in
        the EOF-fenced family, whose source has no body to hold one.
    """

    source_bytes: bytes
    body: bytes
    document: model.Document
    frontmatter: YamlFrontmatter
    prefix_bytes: bytes
    protected_end: int
    body_span: ir_view.SourceSpan | None


@functools.cache
def frontmatter_cases() -> tuple[FrontmatterCase, ...]:
    """Extract every generated terminated-fence source once, in a fixed order.

    The product is small -- shapes times endings times mark presence -- and
    building it once keeps each property's examples drawn from the same
    reviewed set rather than re-extracting on every draw.

    Returns
    -------
    tuple[FrontmatterCase, ...]
        One case per generated source the terminated family can build.
    """
    cases: list[FrontmatterCase] = []
    for yaml_lines in _YAML_BLOCKS:
        for newline in ("\n", "\r\n", "\r"):
            for has_bom in (False, True):
                case = _build_case(yaml_lines, newline, has_bom=has_bom)
                if case is not None:
                    cases.append(case)
    return tuple(cases)


@functools.cache
def eof_fenced_cases() -> tuple[FrontmatterCase, ...]:
    """Extract every generated source whose closing fence ends the file.

    Returns
    -------
    tuple[FrontmatterCase, ...]
        One case per shape, ending, and mark presence, each with no body span
        because its source has no body.
    """
    cases: list[FrontmatterCase] = []
    for yaml_lines in _YAML_BLOCKS:
        for newline in ("\n", "\r\n", "\r"):
            for has_bom in (False, True):
                case = _build_case(
                    yaml_lines, newline, has_bom=has_bom, terminated=False
                )
                if case is not None:
                    cases.append(case)
    return tuple(cases)


def _build_case(
    yaml_lines: tuple[str, ...],
    newline: str,
    *,
    has_bom: bool,
    terminated: bool = True,
) -> FrontmatterCase | None:
    """Extract one generated source, or ``None`` when it breaks an assumption."""
    text = _document_text(yaml_lines, newline, terminated=terminated)
    source_bytes = ((_BOM_TEXT if has_bom else "") + text).encode()
    view = OffsetView.of(source_bytes)
    document = engine.extract_document(
        source_bytes.decode("utf-8-sig"), model.Syntax.MARKDOWN
    )
    frontmatter = yaml_frontmatter(document, view.body)
    if frontmatter is None or frontmatter.prefix_bytes is None:
        return None
    if frontmatter.protected_end is None:
        return None
    body_span = _body_span(document, frontmatter.protected_end)
    if body_span is None and terminated:
        return None
    return FrontmatterCase(
        source_bytes,
        view.body,
        document,
        frontmatter,
        frontmatter.prefix_bytes,
        frontmatter.protected_end,
        body_span,
    )


def _document_text(
    yaml_lines: tuple[str, ...],
    newline: str,
    *,
    terminated: bool,
) -> str:
    """Lay out a frontmatter block and, when terminated, two body paragraphs."""
    block = newline.join(("---", *yaml_lines, "---"))
    if not terminated:
        return block
    paragraphs = newline.join(("Café prose.", "", "Second paragraph."))
    return block + newline + newline + paragraphs + newline


def _body_span(
    document: model.Document,
    protected_end: int,
) -> ir_view.SourceSpan | None:
    """Return the first source-backed span starting after the protected prefix.

    A span that merely starts after the prefix is not enough: the planner
    checks the whole span, so an edit replacing it has to leave the source
    otherwise untouched. The first such span is the whole of the first body
    paragraph in every generated shape, which makes the replacement an
    obvious, reviewable body edit.

    Returns
    -------
    ir_view.SourceSpan | None
        The first source-backed span wholly after ``protected_end``, or
        ``None`` when the source has no such span.
    """
    return next(
        (
            span
            for span in ir_view.source_backed_spans(document)
            if span.byte_start >= protected_end
        ),
        None,
    )


@st.composite
def frontmatter_case(draw: st.DrawFn) -> FrontmatterCase:
    """Draw one generated frontmatter source with a body span after its prefix.

    Returns
    -------
    FrontmatterCase
        A case whose ``frontmatter`` is verifiable and whose ``body_span``
        lies wholly beyond the protected prefix.

    Examples
    --------
    >>> from tests.support.frontmatter_strategies import frontmatter_cases
    >>> bool(frontmatter_cases())
    True
    """
    return draw(st.sampled_from(frontmatter_cases()))


@st.composite
def eof_fenced_case(draw: st.DrawFn) -> FrontmatterCase:
    """Draw one generated source whose closing fence ends the file.

    Returns
    -------
    FrontmatterCase
        A case whose ``protected_end`` is the end of its ``body`` and whose
        ``body_span`` is therefore ``None``.
    """
    return draw(st.sampled_from(eof_fenced_cases()))


def character_boundaries(
    body: bytes,
    span: ir_view.SourceSpan,
) -> tuple[int, ...]:
    """Return every UTF-8 code-point boundary within one source span.

    A byte offset mid-character is refused as ``fix-error/non-utf8-boundary``,
    so a generated edit that wants to exercise an acceptance has to land on one
    of these rather than on an arbitrary integer.

    Returns
    -------
    tuple[int, ...]
        Offsets from ``span.byte_start`` to ``span.byte_end`` inclusive, one
        per code-point boundary in the span's decoded text.
    """
    offset = span.byte_start
    boundaries = [offset]
    for character in body[span.byte_start : span.byte_end].decode():
        offset += len(character.encode())
        boundaries.append(offset)
    return tuple(boundaries)


def replacement_text() -> st.SearchStrategy[str]:
    """Draw non-empty body text that cannot be mistaken for metadata.

    The text avoids ``---`` and any ``-`` so a generated repair cannot turn
    the document's first line into a fence: those cases already have their own
    contract in `test_fix_frontmatter.py`, and here they would measure
    recognition rather than preservation. It is non-empty because an empty
    replacement at a boundary is a no-op rather than the mutation a property
    meant to exercise, and the planner reports the two the same way.

    Surrogates (category ``Cs``) are excluded. Hypothesis draws them by
    default, and a lone surrogate cannot be encoded into the bytes an edit
    splices, so a draw would abort the property inside the splice kernel with
    a `UnicodeEncodeError` that says nothing about the guard.

    Returns
    -------
    st.SearchStrategy[str]
        Non-empty text of at most twelve characters, free of hyphens and line
        endings.
    """
    return st.text(
        alphabet=st.characters(
            blacklist_characters="-\r\n",
            blacklist_categories=("Cs",),
        ),
        min_size=1,
        max_size=12,
    )
