"""Property tests for the pure fix-planning splice kernel."""

import typing as typ

import hypothesis as hyp
import hypothesis.strategies as st
from stilyagi.fixes import TextEdit

from tests.support.assertions import assert_with_context

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
