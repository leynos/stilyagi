"""Check the per-code suppression index used by :class:`SuppressionPlan`.

The index replaces a linear scan of every directive for every finding, so
these tests pin the properties that make one bisection sufficient: spans are
sorted by start, and a running maximum of the ends still covers a start after
a later short span has ended.
"""

from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import (
    InlineSuppression,
    RuleInterval,
    SuppressionPlan,
)


def _plan(
    intervals: tuple[RuleInterval, ...] = (),
    inline: tuple[InlineSuppression, ...] = (),
) -> SuppressionPlan:
    """Build a plan with no file-wide suppression for a focused lookup test."""
    return SuppressionPlan(frozenset(), intervals, inline)


class TestIntervalOrdering:
    """The index must not depend on the order intervals were resolved in."""

    def test_out_of_order_intervals_are_sorted_by_start(self) -> None:
        """A later-listed span starting earlier still covers an inside start."""
        plan = _plan((
            RuleInterval("STY001", 20, 30),
            RuleInterval("STY001", 5, 100),
        ))
        assert plan.suppresses("STY001", SourceSpan(10, 11)), (
            "expected the span starting at 5 to cover byte 10 regardless of "
            "the order intervals were supplied in"
        )

    def test_running_maximum_covers_a_start_after_a_short_span(self) -> None:
        """An earlier long span still covers starts past a later short one."""
        plan = _plan((
            RuleInterval("STY001", 0, 100),
            RuleInterval("STY001", 10, 20),
        ))
        assert plan.suppresses("STY001", SourceSpan(50, 51)), (
            "expected the span (0, 100) to cover byte 50 even though the "
            "latest span starting at or before it ended at 20"
        )


class TestLookupBoundaries:
    """Lookups must respect code membership and half-open bounds."""

    def test_unindexed_code_is_not_suppressed(self) -> None:
        """A code with no spans is never suppressed by ranges or inline."""
        plan = _plan((RuleInterval("STY001", 0, 100),))
        assert not plan.suppresses("STY002", SourceSpan(50, 51)), (
            "expected a code absent from the index to remain unsuppressed"
        )

    def test_start_before_first_span_is_not_suppressed(self) -> None:
        """A start preceding every indexed span falls outside them."""
        plan = _plan((RuleInterval("STY001", 10, 20),))
        assert not plan.suppresses("STY001", SourceSpan(9, 10)), (
            "expected byte 9 to fall before the first span starting at 10"
        )

    def test_start_at_byte_end_is_not_suppressed(self) -> None:
        """Spans are half-open, so the end byte itself is outside."""
        plan = _plan((RuleInterval("STY001", 10, 20),))
        assert not plan.suppresses("STY001", SourceSpan(20, 21)), (
            "expected the half-open span (10, 20) to exclude byte 20"
        )


class TestInlineSuppressions:
    """Inline directives are indexed under every code they name."""

    def test_inline_suppression_covers_each_named_code(self) -> None:
        """One unit span suppresses both codes it lists."""
        plan = _plan(
            inline=(InlineSuppression(("STY001", "STY002"), SourceSpan(30, 40)),)
        )
        assert plan.suppresses("STY001", SourceSpan(35, 36)), (
            "expected STY001 to be suppressed inside the inline unit"
        )
        assert plan.suppresses("STY002", SourceSpan(35, 36)), (
            "expected STY002 to be suppressed inside the inline unit"
        )
        assert not plan.suppresses("STY003", SourceSpan(35, 36)), (
            "expected a code the inline directive does not name to remain unsuppressed"
        )
