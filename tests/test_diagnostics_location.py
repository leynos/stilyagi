"""Tests for converting IR byte offsets into source locations."""

import hypothesis as hyp
import hypothesis.strategies as st
import pytest
from stilyagi.diagnostics_location import line_column_from_offset

from tests.support.assertions import assert_with_context

ASCII_TEXT = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        exclude_characters="\n",
    ),
    min_size=1,
    max_size=12,
)


def line_index_for(source: str) -> tuple[int, ...]:
    """Return byte offsets for line starts plus the end-of-document offset."""
    offsets = [0]
    source_bytes = source.encode("utf-8")
    for offset, byte in enumerate(source_bytes):
        if byte == ord("\n"):
            offsets.append(offset + 1)
    if offsets[-1] != len(source_bytes):
        offsets.append(len(source_bytes))
    return tuple(offsets)


def test_line_column_from_offset_uses_the_line_index_boundaries() -> None:
    """Map offsets to 1-based line and column positions."""
    line_index = (0, 6, 12)

    assert_with_context(
        line_column_from_offset(line_index, 0) == (1, 1),
        "expected line_column_from_offset(line_index, 0) == (...",
    )
    assert_with_context(
        line_column_from_offset(line_index, 7) == (2, 2),
        "expected line_column_from_offset(line_index, 7) == (...",
    )
    assert_with_context(
        line_column_from_offset(line_index, 11) == (2, 6),
        "expected line_column_from_offset(line_index, 11) == ...",
    )


def test_line_column_from_offset_falls_back_without_line_index() -> None:
    """Treat absent line metadata as the first source location."""
    assert_with_context(
        line_column_from_offset(None, 7) == (1, 1),
        "expected line_column_from_offset(None, 7) == (1, 1)",
    )
    assert_with_context(
        line_column_from_offset((), 7) == (1, 1),
        "expected line_column_from_offset((), 7) == (1, 1)",
    )


@pytest.mark.parametrize(
    "line_index",
    [(-1, 6), (6, 3), (0, 6, 6)],
    ids=("negative-start", "decreasing-starts", "duplicate-starts"),
)
def test_line_column_from_offset_falls_back_for_invalid_line_indexes(
    line_index: tuple[int, ...],
) -> None:
    """Treat malformed line metadata as the first source location."""
    assert_with_context(
        line_column_from_offset(line_index, 7) == (1, 1),
        "expected invalid line indexes to fall back to (1, 1)",
    )


@hyp.given(data=st.data())
@hyp.settings(max_examples=64)
def test_line_column_from_offset_is_monotonic_and_in_bounds(
    data: st.DataObject,
) -> None:
    """Keep line numbers stable as the offset increases."""
    lines = data.draw(
        st.lists(ASCII_TEXT, min_size=1, max_size=5),
        label="lines",
    )
    source = "\n".join(lines)
    line_index = line_index_for(source)
    max_offset = max(0, len(source.encode("utf-8")) - 1)
    first_offset = data.draw(st.integers(min_value=0, max_value=max_offset))
    second_offset = data.draw(
        st.integers(min_value=first_offset, max_value=max_offset),
    )

    first_line, first_column = line_column_from_offset(line_index, first_offset)
    second_line, second_column = line_column_from_offset(
        line_index,
        second_offset,
    )

    assert_with_context(
        1 <= first_line <= len(line_index) - 1,
        "expected 1 <= first_line <= len(line_index) - 1",
    )
    assert_with_context(
        1 <= second_line <= len(line_index) - 1,
        "expected 1 <= second_line <= len(line_index) - 1",
    )
    assert first_line <= second_line, "expected first_line <= second_line"
    if first_line == second_line:
        assert first_column <= second_column, "expected first_column <= second_column"
