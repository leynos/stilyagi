"""Property tests for the pure fix-planning splice kernel."""

import typing as typ

import hypothesis as hyp
import hypothesis.strategies as st
from stilyagi import config, diagnostics
from stilyagi.engine import ir_view
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import Applicability, Fix, FixLevel, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.fix_plan_strategies import (
    CorpusSpanCase,
    admissible_edit_cases,
    corpus_span_cases,
    synthetic_straddling_edit_cases,
)

_Value = typ.TypeVar("_Value")


class _StrategyDrawer(typ.Protocol):
    """Draw values from Hypothesis strategies."""

    def __call__(self, strategy: st.SearchStrategy[_Value]) -> _Value:
        """Draw and return a strategy value."""


@st.composite
def source_and_non_overlapping_edits(
    draw: _StrategyDrawer,
) -> tuple[bytes, tuple[TextEdit, ...]]:
    """Construct source bytes and sorted, non-overlapping edits."""
    source = draw(st.binary(max_size=64))
    edit_count = draw(st.integers(min_value=1, max_value=min(6, len(source) + 1)))
    starts = sorted(
        draw(
            st.lists(
                st.integers(min_value=0, max_value=len(source)),
                min_size=edit_count,
                max_size=edit_count,
                unique=True,
            ),
        ),
    )
    edits = tuple(
        TextEdit(
            byte_start=start,
            byte_end=draw(
                st.integers(
                    min_value=start,
                    max_value=next_start,
                ),
            ),
            replacement=draw(st.text(max_size=12)),
        )
        for start, next_start in zip(starts, (*starts[1:], len(source)), strict=True)
    )
    return source, edits


def apply_edits_naively(source: bytes, edits: tuple[TextEdit, ...]) -> bytes:
    """Apply edits right to left as an independent splice oracle."""
    after = source
    for edit in reversed(tuple(sorted(dict.fromkeys(edits)))):
        replacement = edit.replacement.encode()
        after = after[: edit.byte_start] + replacement + after[edit.byte_end :]
    return after


@hyp.given(case=source_and_non_overlapping_edits())
@hyp.settings(max_examples=64)
def test_splice_matches_an_independent_right_to_left_oracle(
    case: tuple[bytes, tuple[TextEdit, ...]],
) -> None:
    """The cursor splice agrees with a deliberately separate implementation."""
    from stilyagi.engine.fix_planning.splice import apply_edits

    source, edits = case

    assert_with_context(
        apply_edits(source, edits) == apply_edits_naively(source, edits),
        "expected the production splice to match the right-to-left oracle",
    )


@hyp.given(case=source_and_non_overlapping_edits())
@hyp.settings(max_examples=64)
def test_splice_length_matches_the_byte_arithmetic(
    case: tuple[bytes, tuple[TextEdit, ...]],
) -> None:
    """The resulting length accounts for removed and inserted UTF-8 bytes."""
    from stilyagi.engine.fix_planning.splice import apply_edits

    source, edits = case
    expected_length = (
        len(source)
        - sum(edit.byte_end - edit.byte_start for edit in dict.fromkeys(edits))
        + sum(len(edit.replacement.encode()) for edit in dict.fromkeys(edits))
    )

    assert_with_context(
        len(apply_edits(source, edits)) == expected_length,
        "expected the splice result length to match the edit byte arithmetic",
    )


@hyp.given(case=source_and_non_overlapping_edits(), data=st.data())
@hyp.settings(max_examples=64)
def test_splice_is_deterministic_for_every_edit_permutation(
    case: tuple[bytes, tuple[TextEdit, ...]],
    data: st.DataObject,
) -> None:
    """Caller ordering cannot affect byte-splice output."""
    from stilyagi.engine.fix_planning.splice import apply_edits

    source, edits = case
    permutation = data.draw(st.permutations(edits))

    assert_with_context(
        apply_edits(source, edits) == apply_edits(source, permutation),
        "expected every permutation to produce identical splice output",
    )


@hyp.given(case=source_and_non_overlapping_edits())
@hyp.settings(max_examples=64)
def test_splice_coalesces_exact_duplicate_edits(
    case: tuple[bytes, tuple[TextEdit, ...]],
) -> None:
    """Adding an exact duplicate does not alter the resulting bytes."""
    from stilyagi.engine.fix_planning.splice import apply_edits

    source, edits = case
    duplicate = edits[:1] or (TextEdit(0, 0, ""),)

    assert_with_context(
        apply_edits(source, edits) == apply_edits(source, (*edits, *duplicate)),
        "expected an exact duplicate edit to be coalesced",
    )


def _request(
    case: CorpusSpanCase, diagnostics_list: tuple[diagnostics.Diagnostic, ...]
) -> FixPlanRequest:
    """Build a permissive safe-fix planning request for one corpus case."""
    return FixPlanRequest(
        case.source_bytes,
        case.document,
        diagnostics_list,
        FixLevel.SAFE,
        config.LintConfig(),
    )


def _diagnostic(code: str, edit: TextEdit) -> diagnostics.Diagnostic:
    """Build one safe corpus edit diagnostic."""
    return diagnostics.Diagnostic(
        "tests/fixture.md",
        code,
        "example",
        fix=Fix("Replace prose", Applicability.SAFE, (edit,)),
    )


@hyp.given(case=admissible_edit_cases())
@hyp.settings(max_examples=64, deadline=None)
def test_accepted_edits_stay_inside_one_source_backed_span(
    case: CorpusSpanCase,
) -> None:
    """Constructively drawn source edits remain accepted within one merged span."""
    edit = TextEdit.replace(case.span, "replacement")

    plan = plan_fixes(_request(case, (_diagnostic("PUN201", edit),)))

    assert_with_context(plan.fixed_bytes is not None, "expected a contained edit")
    assert_with_context(
        all(
            any(
                source_span.byte_start
                <= planned.byte_start
                <= planned.byte_end
                <= source_span.byte_end
                for source_span in ir_view.source_backed_spans(case.document)
            )
            for planned in plan.edits
        ),
        "expected every accepted edit to lie in one source-backed span",
    )


@hyp.given(case=synthetic_straddling_edit_cases())
@hyp.settings(max_examples=64, deadline=None)
def test_synthetic_straddling_edits_always_abort_mutation(case: CorpusSpanCase) -> None:
    """Edits constructed across a synthetic segment never produce fixed bytes."""
    edit = TextEdit.replace(case.span, "replacement")

    plan = plan_fixes(_request(case, (_diagnostic("PUN201", edit),)))

    assert_with_context(
        plan.fixed_bytes is None,
        "expected a source-to-synthetic span to abort the entire file plan",
    )
    assert_with_context(bool(plan.rejections), "expected a synthetic-span rejection")


@hyp.given(case=admissible_edit_cases())
@hyp.settings(max_examples=64, deadline=None)
def test_conflicting_edits_never_produce_fixed_bytes(case: CorpusSpanCase) -> None:
    """Two different replacements for one admissible span preserve the source."""
    first = _diagnostic("PUN201", TextEdit.replace(case.span, "first"))
    second = _diagnostic("PUN202", TextEdit.replace(case.span, "second"))

    plan = plan_fixes(_request(case, (first, second)))

    assert_with_context(
        plan.fixed_bytes is None, "expected a conflict to leave the source untouched"
    )


@hyp.given(case=st.sampled_from(corpus_span_cases()))
@hyp.settings(max_examples=64, deadline=None)
def test_empty_plans_preserve_every_corpus_source(case: CorpusSpanCase) -> None:
    """No eligible fixes is an identity transformation for every corpus file."""
    plan = plan_fixes(_request(case, ()))

    assert_with_context(
        plan.fixed_bytes == case.source_bytes,
        "expected a plan without diagnostics to preserve the original bytes",
    )


@hyp.given(case=admissible_edit_cases())
@hyp.settings(max_examples=64, deadline=None)
def test_accepted_plans_remain_valid_utf8(case: CorpusSpanCase) -> None:
    """UTF-8-aligned accepted edits always leave decodable source bytes."""
    edit = TextEdit.replace(case.span, "replaced with é")

    plan = plan_fixes(_request(case, (_diagnostic("PUN201", edit),)))

    assert_with_context(plan.fixed_bytes is not None, "expected a contained edit")
    assert_with_context(
        plan.fixed_bytes.decode() is not None,
        "expected accepted UTF-8 edits to yield decodable source bytes",
    )
