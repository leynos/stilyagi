"""Tests for shared assertion diagnostics."""

import pytest

from tests.support.assertions import assert_with_context


def test_assert_with_context_accepts_truthy_conditions() -> None:
    """Return normally when the asserted condition is true."""
    assert_with_context(2 + 2 == 4, "the condition should pass")


def test_assert_with_context_reports_supplied_diagnostic() -> None:
    """Preserve the caller's diagnostic when the assertion fails."""
    with pytest.raises(AssertionError, match="the condition should fail"):
        assert_with_context(2 + 2 == 5, "the condition should fail")
