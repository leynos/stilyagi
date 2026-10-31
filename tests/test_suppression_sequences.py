"""Generated directive sequences checked against an independent replay.

Handwritten cases in :mod:`tests.test_rule_policy` pin the interesting shapes
of the suppression state machine; this module covers the rest of the space. It
draws range events, ``ignore-next`` directives, and prose units together, then
compares the resolved plan with a direct replay that folds nothing into
intervals. The replay is written from the documented semantics rather than
from the plan, so a shared mistake in the resolver cannot satisfy both sides.
"""

import dataclasses as dc
import operator
import typing as typ
from itertools import starmap

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from stilyagi import model
from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import resolve_suppressions

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_INVENTORY = ("STY001", "STY002")
_SOURCE_LENGTH = 100
_UNIT_WIDTH = 3
_UNIT_SPACING = 8
_FIRST_UNIT_START = 8
_CODE_SETS = (
    ("STY001",),
    ("STY002",),
    ("STY001", "STY002"),
    ("STY",),
)


@dc.dataclass(frozen=True, slots=True)
class _SuppressionCase:
    """One generated directive sequence with the units it may consume."""

    events: tuple[tuple[int, str, tuple[str, ...]], ...]
    inline: tuple[tuple[int, tuple[str, ...]], ...]
    units: tuple[tuple[int, int], ...]
    queries: tuple[tuple[str, int], ...]

    def suppresses(self, code: str, offset: int) -> bool:
        """Replay the sequence directly for one code and offset.

        Range events are replayed per queried code rather than folded into
        intervals, and each ``ignore-next`` directive consumes the next unit at
        or after its end, matching the documented "next nonempty unit"
        semantics. Both checks are independent of the resolved plan.

        Returns
        -------
        bool
            ``True`` when a range or inline directive covers the offset.
        """
        return self._range_covers(code, offset) or self._inline_covers(code, offset)

    def _range_covers(self, code: str, offset: int) -> bool:
        """Replay range events for one code and offset.

        Returns
        -------
        bool
            ``True`` when the last relevant event at or before the offset
            opened a suppression range.
        """
        state = False
        for position, role, codes in sorted(self.events, key=operator.itemgetter(0)):
            if position > offset:
                break
            if code in _expand(codes):
                state = role == "open"
        return state

    def _inline_covers(self, code: str, offset: int) -> bool:
        """Bind each inline directive to one unit and test containment.

        Returns
        -------
        bool
            ``True`` when a consumed unit covering the offset names the code.
        """
        cursor = 0
        for directive_end, codes in self.inline:
            while cursor < len(self.units) and self.units[cursor][0] < directive_end:
                cursor += 1
            if cursor == len(self.units):
                continue
            unit_start, unit_end = self.units[cursor]
            cursor += 1
            if code in _expand(codes) and unit_start <= offset < unit_end:
                return True
        return False


def _expand(prefixes: cabc.Sequence[str]) -> frozenset[str]:
    """Expand generated prefixes against the two-code inventory."""
    return frozenset(
        code
        for code in _INVENTORY
        if "ALL" in prefixes or any(code.startswith(prefix) for prefix in prefixes)
    )


@st.composite
def _suppression_case(draw: st.DrawFn) -> _SuppressionCase:
    """Build a valid directive sequence with unambiguous unit gaps."""
    slots = sorted(draw(st.sets(st.integers(min_value=0, max_value=4))))
    unit_starts = tuple(_FIRST_UNIT_START + _UNIT_SPACING * slot for slot in slots)
    events = tuple(
        draw(
            st.lists(
                st.tuples(
                    st.integers(min_value=0, max_value=_SOURCE_LENGTH),
                    st.sampled_from(["open", "close"]),
                    st.sampled_from(_CODE_SETS),
                ),
                max_size=6,
                unique_by=operator.itemgetter(0),
            )
        )
    )
    inline = tuple(
        (start - 3, draw(st.sampled_from(_CODE_SETS)))
        for start in unit_starts
        if draw(st.booleans())
    )
    return _SuppressionCase(
        events=events,
        inline=inline,
        units=tuple((start, start + _UNIT_WIDTH) for start in unit_starts),
        queries=tuple(
            (code, offset) for code in _INVENTORY for offset in range(_SOURCE_LENGTH)
        ),
    )


def _raw_suppressions(case: _SuppressionCase) -> list[dict[str, object]]:
    """Return IR suppression entries for one generated case."""
    ranges: list[dict[str, object]] = [
        {
            "kind": "range",
            "range_role": role,
            "codes": list(codes),
            "span": {"byte_start": position, "byte_end": position},
        }
        for position, role, codes in case.events
    ]
    inline: list[dict[str, object]] = [
        {
            "kind": "inline",
            "codes": list(codes),
            "span": {"byte_start": directive_end - 1, "byte_end": directive_end},
        }
        for directive_end, codes in case.inline
    ]
    return ranges + inline


@settings(max_examples=80, deadline=None)
@given(case=_suppression_case())
def test_generated_suppression_sequences_match_a_direct_replay(
    case: _SuppressionCase,
) -> None:
    """Ranges and ``ignore-next`` agree with an independent replay."""
    plan = resolve_suppressions(
        model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"suppressions": _raw_suppressions(case)},
        ),
        concrete_codes=_INVENTORY,
        source_length=_SOURCE_LENGTH,
        prose_units=tuple(starmap(SourceSpan, case.units)),
    )
    oracle = {
        (code, offset): case.suppresses(code, offset) for code, offset in case.queries
    }
    assume(any(oracle.values()) and not all(oracle.values()))

    for (code, offset), expected in oracle.items():
        assert plan.suppresses(code, SourceSpan(offset, offset + 1)) is expected, (
            case,
            code,
            offset,
        )
