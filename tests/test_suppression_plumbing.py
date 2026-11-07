"""Resolved suppression plans, exercised from handwritten IR.

These cases pin what a plan decides once the directives are already parsed:
which codes a range toggles, where a range ends, and which malformed entries
are dropped rather than raised. They build the document directly, so a failure
points at the plan rather than at extraction or at rule selection. The policy
truth tables live in :mod:`tests.test_rule_policy`; the generated sequences
live in :mod:`tests.test_suppression_sequences`.
"""

import dataclasses as dc

import pytest
from stilyagi import model
from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import (
    IgnoreDirective,
    SuppressionPlan,
    resolve_suppressions,
)

_OPEN_AT = (0, 5)
_CLOSE_AT = (10, 15)


def _span(start: int, end: int) -> dict[str, int]:
    """Return the IR mapping for one byte span."""
    return {"byte_start": start, "byte_end": end}


def _range(
    role: str,
    codes: list[str],
    span: tuple[int, int] | None,
) -> dict[str, object]:
    """Return one range-directive IR entry."""
    entry: dict[str, object] = {"kind": "range", "range_role": role, "codes": codes}
    if span is not None:
        entry["span"] = _span(*span)
    return entry


def _file(codes: list[str]) -> dict[str, object]:
    """Return one file-directive IR entry."""
    return {"kind": "file", "codes": codes, "span": None}


@dc.dataclass(frozen=True, slots=True)
class _ToggleCase:
    """One open/close pair, and the query it is expected to answer."""

    open_codes: tuple[str, ...]
    close_codes: tuple[str, ...]
    code: str
    span: tuple[int, int]
    is_suppressed: bool


class TestSuppressionPlumbing:
    """Resolved plans expose their decisions without exercising a rule."""

    @staticmethod
    def _plan(
        suppressions: list[dict[str, object]],
        *,
        codes: tuple[str, ...] = ("STY001", "STY002"),
        source_length: int = 100,
    ) -> SuppressionPlan:
        """Resolve suppressions from handwritten IR entries."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"suppressions": suppressions},
        )
        return resolve_suppressions(
            document,
            concrete_codes=codes,
            source_length=source_length,
        )

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                _ToggleCase(
                    ("STY",), ("STY001",), "STY002", (20, 21), is_suppressed=True
                ),
                id="sibling-stays",
            ),
            pytest.param(
                _ToggleCase(
                    ("STY",), ("STY001",), "STY001", (20, 21), is_suppressed=False
                ),
                id="re-enabled-live",
            ),
            pytest.param(
                _ToggleCase(
                    ("STY001",), ("STY001",), "STY001", (9, 12), is_suppressed=True
                ),
                id="inside-range",
            ),
            pytest.param(
                _ToggleCase(
                    ("STY001",), ("STY001",), "STY001", (10, 12), is_suppressed=False
                ),
                id="at-boundary",
            ),
        ],
    )
    def test_an_open_close_pair_toggles_by_code_and_position(
        self, case: _ToggleCase
    ) -> None:
        """A close event ends its own codes at its start, and no others.

        The first two cases pin code granularity: ``disable STY`` followed by
        ``enable STY001`` reopens one code and leaves its sibling suppressed.
        The last two pin position granularity: the close boundary is exclusive,
        so a finding that starts there is live while one that starts earlier is
        not.
        """
        plan = self._plan([
            _range("open", list(case.open_codes), _OPEN_AT),
            _range("close", list(case.close_codes), _CLOSE_AT),
        ])

        assert (
            plan.suppresses(case.code, SourceSpan(*case.span)) is case.is_suppressed
        ), f"expected {case.code} at {case.span} to be suppressed={case.is_suppressed}"

    def test_a_finding_without_a_span_escapes_located_directives(self) -> None:
        """Only file suppression can hide an unlocated finding."""
        plan = self._plan([_file(["STY001"])])

        assert plan.suppresses("STY001", None), (
            "expected file suppression to hide an unlocated finding"
        )
        assert not plan.suppresses("STY002", None), (
            "expected a file directive for another code not to apply"
        )

    def test_a_non_string_kind_is_ignored(self) -> None:
        """A directive whose kind is not a string cannot be interpreted."""
        plan = self._plan([{"kind": 3, "codes": ["STY001"]}])

        assert not plan.suppresses("STY001", SourceSpan(0, 1)), (
            "expected a non-string kind to be ignored"
        )

    def test_codes_that_expand_to_nothing_are_ignored(self) -> None:
        """A directive naming no known code suppresses nothing."""
        plan = self._plan([_file(["NOPE"])])

        assert not plan.suppresses("STY001", None), (
            "expected an unknown code to expand to nothing"
        )

    def test_a_range_event_without_a_span_is_ignored(self) -> None:
        """A range event with no position cannot open or close a range."""
        plan = self._plan([_range("open", ["STY001"], None)])

        assert not plan.suppresses("STY001", SourceSpan(0, 1)), (
            "expected a spanless range event to be ignored"
        )

    def test_a_malformed_span_is_ignored(self) -> None:
        """A reversed span is dropped rather than raising."""
        plan = self._plan([_range("open", ["STY001"], (4, 1))])

        assert not plan.suppresses("STY001", SourceSpan(0, 1)), (
            "expected a malformed span to be ignored"
        )

    def test_ignore_directive_covers_only_its_codes(self) -> None:
        """The directive's own predicate is a plain membership test."""
        directive = IgnoreDirective(("STY001",), None, "file", None)

        assert directive.covers("STY001"), "expected the directive to cover its code"
        assert not directive.covers("STY002"), (
            "expected the directive not to cover another code"
        )
