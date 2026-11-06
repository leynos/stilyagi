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

from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi import model
from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import SuppressionPlan, resolve_suppressions

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
        """Bind each inline directive independently to its next unit.

        The resolver resolves every directive on its own, so two directives
        before the same unit both bind to it. A shared advancing cursor would
        instead bind them to successive units and disagree with production.

        Returns
        -------
        bool
            ``True`` when a bound unit covering the offset names the code.
        """
        for directive_end, codes in self.inline:
            unit = next((unit for unit in self.units if unit[0] >= directive_end), None)
            if unit is None or code not in _expand(codes):
                continue
            unit_start, unit_end = unit
            if unit_start <= offset < unit_end:
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
        (directive_end, draw(st.sampled_from(_CODE_SETS)))
        for directive_end in sorted(
            draw(
                st.sets(
                    st.integers(min_value=1, max_value=_SOURCE_LENGTH - 1),
                    max_size=4,
                )
            )
        )
    )
    return _named_case(events=events, inline=inline, unit_starts=unit_starts)


def _named_case(
    *,
    events: tuple[tuple[int, str, tuple[str, ...]], ...] = (),
    inline: tuple[tuple[int, tuple[str, ...]], ...] = (),
    unit_starts: tuple[int, ...] = (_FIRST_UNIT_START,),
) -> _SuppressionCase:
    """Build a named case over the standard code/offset query grid."""
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


def _resolve(case: _SuppressionCase) -> SuppressionPlan:
    """Resolve the plan one generated case describes."""
    return resolve_suppressions(
        model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"suppressions": _raw_suppressions(case)},
        ),
        concrete_codes=_INVENTORY,
        source_length=_SOURCE_LENGTH,
        prose_units=tuple(starmap(SourceSpan, case.units)),
    )


def _assert_matches_replay(case: _SuppressionCase) -> None:
    """Compare the resolved plan with the direct replay over every query."""
    plan = _resolve(case)
    for code, offset in case.queries:
        expected = case.suppresses(code, offset)
        assert plan.suppresses(code, SourceSpan(offset, offset + 1)) is expected, (
            case,
            code,
            offset,
        )


@settings(max_examples=80, deadline=None)
@given(case=_suppression_case())
def test_generated_suppression_sequences_match_a_direct_replay(
    case: _SuppressionCase,
) -> None:
    """Ranges and ``ignore-next`` agree with an independent replay."""
    _assert_matches_replay(case)


def test_named_witnesses_cover_states_the_property_must_reach() -> None:
    """Named histories keep the unfiltered property non-vacuous.

    Without outcome-dependent filtering a generated example may suppress
    nothing or everything. These witnesses always exercise an empty history,
    an active-to-inactive transition, a consumed next unit, two directives
    before one unit, and a directive with no following unit.
    """
    empty = _named_case()
    assert not any(starmap(empty.suppresses, empty.queries)), (
        "an empty history must suppress nothing"
    )

    transition = _named_case(
        events=((10, "open", ("STY001",)), (20, "close", ("STY001",)))
    )
    states = {
        transition.suppresses("STY001", offset) for offset in range(_SOURCE_LENGTH)
    }
    assert states == {False, True}, "the transition must reach both states"

    bound = _named_case(inline=((5, ("STY001",)),))
    assert bound.suppresses("STY001", _FIRST_UNIT_START), (
        "the directive must consume the next unit"
    )
    assert not bound.suppresses("STY001", _FIRST_UNIT_START - 1), (
        "the directive must not reach the preceding byte"
    )

    shared = _named_case(inline=((5, ("STY001",)), (6, ("STY002",))))
    assert shared.suppresses("STY001", _FIRST_UNIT_START), (
        "the first directive must bind the shared unit"
    )
    assert shared.suppresses("STY002", _FIRST_UNIT_START), (
        "the second directive must also bind the shared unit"
    )

    orphan = _named_case(inline=((_SOURCE_LENGTH - 1, ("STY001",)),))
    assert not any(starmap(orphan.suppresses, orphan.queries)), (
        "a directive with no following unit must suppress nothing"
    )

    for case in (empty, transition, bound, shared, orphan):
        _assert_matches_replay(case)


def test_ignore_next_binds_the_first_unit_and_not_the_second() -> None:
    """One directive consumes one unit, even when two units follow it.

    The generated property compares the plan against a replay, so a
    resolver that bound every later unit would agree with a replay that did
    the same. This pins the resolved plan itself against the documented
    "next nonempty unit" semantics.
    """
    two_units = _named_case(
        inline=((5, ("STY001",)),),
        unit_starts=(_FIRST_UNIT_START, _FIRST_UNIT_START + _UNIT_SPACING),
    )
    plan = _resolve(two_units)

    assert plan.suppresses(
        "STY001", SourceSpan(_FIRST_UNIT_START, _FIRST_UNIT_START)
    ), "the directive must bind the first unit"
    assert not plan.suppresses(
        "STY001",
        SourceSpan(
            _FIRST_UNIT_START + _UNIT_SPACING,
            _FIRST_UNIT_START + _UNIT_SPACING,
        ),
    ), "the directive must not reach the second unit"
