"""How the timeout readings behave on inputs chosen for a case.

Separated from `test_timeout_ordering_contract`, whose subject is this
repository's own workflows and nextest configuration. These drive the
readings with values the tree does not contain, which is the only way to
tell a correct reading from one that happens to agree with the single
configuration in front of it.
"""

import pytest

from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    UnboundedTestError,
    largest_test_allowance,
    termination_allowance,
)
from tests.test_timeout_ordering_contract import (
    CEILING_MARGIN_SECONDS,
    required_ceiling,
)


@pytest.mark.parametrize(
    ("config_text", "expected"),
    [
        pytest.param(
            'slow-timeout = { period = "180s", terminate-after = 1 }',
            180.0,
            id="a-single-period",
        ),
        pytest.param(
            'slow-timeout = { period = "60s", terminate-after = 5 }',
            300.0,
            id="five-warning-periods",
        ),
        pytest.param(
            'slow-timeout = { period = "2m", terminate-after = 3 }',
            360.0,
            id="minutes-times-three",
        ),
        pytest.param(
            'slow-timeout = { period = "30s", terminate-after = 2, '
            'grace-period = "5s" }\n'
            'slow-timeout = { period = "60s", terminate-after = 1 }',
            60.0,
            id="the-largest-of-several",
        ),
    ],
)
def test_the_largest_per_test_allowance_counts_the_multiplier(
    config_text: str, expected: float
) -> None:
    """``terminate-after`` scales the period; the budget is their product.

    This is the reading every comparison above rests on, and it is the
    one easy to get wrong. It is driven with controlled configurations
    rather than this repository's own, whose multipliers are all one:
    against that file a reading that ignored the multiplier entirely
    would give the same answer, and the test would prove nothing.
    """
    assert largest_test_allowance(config_text) == pytest.approx(expected), (
        f"{config_text!r} must yield a {expected:.0f}s largest per-test "
        f"allowance; terminate-after scales the period"
    )


def test_a_grace_period_is_not_read_as_a_per_test_budget() -> None:
    """The two keys sit in the same inline table.

    A matcher reading `period` as a substring would take a grace period
    for a per-test budget whenever the former were the larger, which
    would silently raise the whole-run budget this contract demands.
    """
    config_text = (
        'slow-timeout = { period = "30s", terminate-after = 1, grace-period = "30m" }'
    )
    assert largest_test_allowance(config_text) == pytest.approx(30.0), (
        "the per-test ceiling read a grace period as a slow-timeout"
    )


def test_the_termination_allowance_is_the_grace_period_plus_the_margin() -> None:
    """The two terms are added, not maximized over.

    A single floor over the grace period and the margin would absorb any
    grace period below the margin, so raising one from five seconds to
    thirty would demand nothing more of the watchdog above it. Adding
    them keeps a raised grace period visible in the requirement.
    """
    unset = termination_allowance("")
    assert unset == pytest.approx(
        NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS + TERMINATION_SAFETY_MARGIN_SECONDS
    ), "an unset grace period must fall back to nextest's own default"
    raised = termination_allowance(
        'slow-timeout = { period = "30s", grace-period = "30s" }'
    )
    assert raised == pytest.approx(30.0 + TERMINATION_SAFETY_MARGIN_SECONDS), (
        "a grace period below the margin must still raise the allowance; "
        "a maximum over the two terms would have discarded it"
    )
    largest = termination_allowance(
        'slow-timeout = { grace-period = "5s" }\n'
        'slow-timeout = { grace-period = "45s" }'
    )
    assert largest == pytest.approx(45.0 + TERMINATION_SAFETY_MARGIN_SECONDS), (
        "the largest configured grace period governs the allowance"
    )


def test_the_required_ceiling_carries_all_three_terms() -> None:
    """Watchdogs, measured work outside them, and the margin.

    Both ceilings sit exactly fifteen minutes above the smaller
    requirement, so the margin is what the current values already carry
    and dropping the term would still leave them passing. Driving the
    derivation with controlled numbers is what makes it visible.
    """
    assert required_ceiling([1800.0, 2700.0], 900.0) == pytest.approx(
        4500.0 + 900.0 + CEILING_MARGIN_SECONDS
    ), "two watchdogs, the allowance and the margin are all added"
    assert required_ceiling([1800.0], 0.0) == pytest.approx(
        1800.0 + CEILING_MARGIN_SECONDS
    ), "the margin applies even when nothing runs outside the watchdog"
    assert required_ceiling([], 0.0) == pytest.approx(CEILING_MARGIN_SECONDS), (
        "the margin is a term of its own, not a fraction of the others"
    )


@pytest.mark.parametrize(
    "config_text",
    [
        pytest.param('slow-timeout = "2m"', id="the-bare-string-form"),
        pytest.param(
            'slow-timeout = { period = "2m" }', id="a-table-without-terminate-after"
        ),
        pytest.param(
            'slow-timeout = { period = "2m", grace-period = "5s" }',
            id="a-table-with-only-a-grace-period",
        ),
    ],
)
def test_a_slow_timeout_that_never_terminates_is_refused(config_text: str) -> None:
    """`terminate-after` is what makes a slow timeout a bound.

    nextest marks a test slow after the period and, without
    `terminate-after`, lets it run for ever. Both the bare string form
    and a table omitting the key do this. Reading either as a
    two-minute budget would report the per-test tier as present when it
    is absent, and the whole-run budget above it would be checked
    against a number nextest never applies.
    """
    with pytest.raises(UnboundedTestError, match=r"terminate-after|warn-only"):
        largest_test_allowance(config_text)
