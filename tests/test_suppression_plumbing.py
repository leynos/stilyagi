"""Resolved suppression plans, exercised from handwritten IR.

These cases pin what a plan decides once the directives are already parsed:
which codes a range toggles, where a range ends, and which malformed entries
are dropped rather than raised. They build the document directly, so a failure
points at the plan rather than at extraction or at rule selection. The policy
truth tables live in :mod:`tests.test_rule_policy`; the generated sequences
live in :mod:`tests.test_suppression_sequences`.
"""

from stilyagi import model
from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import (
    IgnoreDirective,
    SuppressionPlan,
    resolve_suppressions,
)


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

    def test_sibling_codes_toggle_independently(self) -> None:
        """``disable STY`` then ``enable STY001`` leaves STY002 suppressed."""
        plan = self._plan([
            {
                "kind": "range",
                "range_role": "open",
                "codes": ["STY"],
                "span": {"byte_start": 0, "byte_end": 5},
            },
            {
                "kind": "range",
                "range_role": "close",
                "codes": ["STY001"],
                "span": {"byte_start": 10, "byte_end": 15},
            },
        ])

        assert plan.suppresses("STY002", SourceSpan(20, 21)), (
            "expected a sibling code to stay suppressed"
        )
        assert not plan.suppresses("STY001", SourceSpan(20, 21)), (
            "expected the re-enabled code not to be suppressed"
        )

    def test_range_end_is_exclusive(self) -> None:
        """A finding starting at the close boundary is not suppressed."""
        plan = self._plan([
            {
                "kind": "range",
                "range_role": "open",
                "codes": ["STY001"],
                "span": {"byte_start": 0, "byte_end": 5},
            },
            {
                "kind": "range",
                "range_role": "close",
                "codes": ["STY001"],
                "span": {"byte_start": 10, "byte_end": 15},
            },
        ])

        assert plan.suppresses("STY001", SourceSpan(9, 12)), (
            "expected a finding inside the range to be suppressed"
        )
        assert not plan.suppresses("STY001", SourceSpan(10, 12)), (
            "expected the exclusive boundary to stop suppression"
        )

    def test_a_finding_without_a_span_escapes_located_directives(self) -> None:
        """Only file suppression can hide an unlocated finding."""
        plan = self._plan([{"kind": "file", "codes": ["STY001"], "span": None}])

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
        plan = self._plan([{"kind": "file", "codes": ["NOPE"]}])

        assert not plan.suppresses("STY001", None), (
            "expected an unknown code to expand to nothing"
        )

    def test_a_range_event_without_a_span_is_ignored(self) -> None:
        """A range event with no position cannot open or close a range."""
        plan = self._plan([
            {"kind": "range", "range_role": "open", "codes": ["STY001"]},
        ])

        assert not plan.suppresses("STY001", SourceSpan(0, 1)), (
            "expected a spanless range event to be ignored"
        )

    def test_a_malformed_span_is_ignored(self) -> None:
        """A reversed span is dropped rather than raising."""
        plan = self._plan([
            {
                "kind": "range",
                "range_role": "open",
                "codes": ["STY001"],
                "span": {"byte_start": 4, "byte_end": 1},
            },
        ])

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
