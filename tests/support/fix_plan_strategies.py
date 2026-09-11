"""Construct corpus-backed inputs for safe-fix planning properties."""

import dataclasses as dc
import functools
import pathlib
import typing as typ

import hypothesis.strategies as st
from stilyagi import engine, model
from stilyagi.engine import ir_view

_Value = typ.TypeVar("_Value")
_CORPUS_ROOT = pathlib.Path(__file__).parents[1] / "fixtures/corpus/markdown"


class _StrategyDrawer(typ.Protocol):
    """Draw values from Hypothesis strategies."""

    def __call__(self, strategy: st.SearchStrategy[_Value]) -> _Value:
        """Draw and return a strategy value."""


@dc.dataclass(frozen=True, slots=True)
class CorpusSpanCase:
    """One extracted corpus document and a source-backed span within it."""

    source_bytes: bytes
    document: model.Document
    span: ir_view.SourceSpan


@dc.dataclass(frozen=True, slots=True)
class SyntheticStraddleCase:
    """One extracted corpus document with a synthetic span between source spans."""

    source_bytes: bytes
    document: model.Document
    before: ir_view.SourceSpan
    after: ir_view.SourceSpan


@functools.cache
def corpus_paths() -> tuple[pathlib.Path, ...]:
    """Return the shared Markdown corpus paths in deterministic order."""
    return tuple(sorted(_CORPUS_ROOT.rglob("*.md*")))


@functools.cache
def corpus_span_cases() -> tuple[CorpusSpanCase, ...]:
    """Extract every source-backed corpus segment once for property strategies."""
    cases: list[CorpusSpanCase] = []
    for path in corpus_paths():
        source_bytes, document = _extract_document(path)
        cases.extend(
            CorpusSpanCase(source_bytes, document, segment.span)
            for segment in ir_view.iter_segments(document)
            if segment.span is not None
        )
    return tuple(cases)


@functools.cache
def synthetic_straddle_cases() -> tuple[SyntheticStraddleCase, ...]:
    """Extract corpus segments that make a source-to-synthetic edit possible."""
    cases: list[SyntheticStraddleCase] = []
    for path in corpus_paths():
        source_bytes, document = _extract_document(path)
        segments = tuple(ir_view.iter_segments(document))
        cases.extend(
            SyntheticStraddleCase(source_bytes, document, before.span, after.span)
            for before, middle, after in zip(
                segments, segments[1:], segments[2:], strict=False
            )
            if before.span is not None
            and middle.span is None
            and after.span is not None
        )
    return tuple(cases)


@st.composite
def admissible_edit_cases(draw: _StrategyDrawer) -> CorpusSpanCase:
    """Draw an edit span wholly inside one source-backed corpus segment."""
    case = draw(st.sampled_from(corpus_span_cases()))
    boundaries = _character_boundaries(case.source_bytes, case.span)
    start_index = draw(st.integers(min_value=0, max_value=len(boundaries) - 1))
    end_index = draw(st.integers(min_value=start_index, max_value=len(boundaries) - 1))
    return CorpusSpanCase(
        case.source_bytes,
        case.document,
        ir_view.SourceSpan(boundaries[start_index], boundaries[end_index]),
    )


@st.composite
def synthetic_straddling_edit_cases(draw: _StrategyDrawer) -> CorpusSpanCase:
    """Draw a UTF-8-aligned edit that deliberately crosses a synthetic segment."""
    case = draw(st.sampled_from(synthetic_straddle_cases()))
    before_boundaries = _character_boundaries(case.source_bytes, case.before)
    after_boundaries = _character_boundaries(case.source_bytes, case.after)
    start = draw(st.sampled_from(before_boundaries[:-1]))
    end = draw(st.sampled_from(after_boundaries[1:]))
    return CorpusSpanCase(
        case.source_bytes, case.document, ir_view.SourceSpan(start, end)
    )


def _extract_document(path: pathlib.Path) -> tuple[bytes, model.Document]:
    """Read and extract one fixture without normalizing its line endings."""
    source_bytes = path.read_bytes()
    return source_bytes, engine.extract_document(
        source_bytes.decode(), model.Syntax.MARKDOWN
    )


def _character_boundaries(
    source_bytes: bytes, span: ir_view.SourceSpan
) -> tuple[int, ...]:
    """Return every UTF-8 code-point boundary within one source span."""
    offset = span.byte_start
    boundaries = [offset]
    for character in source_bytes[span.byte_start : span.byte_end].decode():
        offset += len(character.encode())
        boundaries.append(offset)
    return tuple(boundaries)
