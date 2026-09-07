"""Property tests for the timeout readings the ordering contract rests on.

The ordering contract compares four numbers. Its example tests pin the
readings against configurations chosen by hand, which proves those
cases and nothing about the ones nobody thought of. These properties
hold over generated configurations instead, so a reading that is right
about `300s` and wrong about `5m`, or right about two profiles and
wrong about seven, fails here rather than in a run that is cancelled
six months from now.

Error paths are covered as well, since a reading that guesses at a
malformed configuration would compare a number nextest never uses.
"""

import typing as typ

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    NextestConfigurationError,
    grace_period,
    largest_test_allowance,
    seconds,
    termination_allowance,
)

#: The units nextest accepts, with their length in seconds.
UNITS: typ.Final[dict[str, float]] = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

whole_numbers = st.integers(min_value=1, max_value=10_000)
units = st.sampled_from(sorted(UNITS))
multipliers = st.integers(min_value=1, max_value=20)


@given(value=whole_numbers, unit=units)
def test_every_unit_scales_the_value(value: int, unit: str) -> None:
    """A duration is its number times the length of its unit.

    Written as a property because the unit table is the one place a
    single wrong entry would go unnoticed: every comparison downstream
    would still be an inequality between two plausible numbers.
    """
    assert seconds(f"{value}{unit}") == pytest.approx(value * UNITS[unit]), (
        f"{value}{unit} must scale by the length of its unit"
    )


@given(
    budgets=st.lists(
        st.tuples(whole_numbers, units, multipliers), min_size=1, max_size=8
    )
)
def test_the_largest_per_test_budget_is_the_largest_product(
    budgets: list[tuple[int, str, int]],
) -> None:
    """Every `slow-timeout` counts, and each counts as a product.

    A reading that took the first entry, or the largest period without
    its multiplier, would agree with the handwritten cases whenever
    they happened to coincide. Over generated configurations they stop
    coinciding.
    """
    config_text = "\n".join(
        f'slow-timeout = {{ period = "{value}{unit}", terminate-after = {times} }}'
        for value, unit, times in budgets
    )
    expected = max(value * UNITS[unit] * times for value, unit, times in budgets)
    assert largest_test_allowance(config_text) == pytest.approx(expected), (
        "the largest per-test budget is the largest period times its multiplier"
    )


@given(periods=st.lists(st.tuples(whole_numbers, units), min_size=1, max_size=6))
def test_the_termination_allowance_tracks_the_largest_grace_period(
    periods: list[tuple[int, str]],
) -> None:
    """The allowance is the largest grace period plus the fixed margin.

    Two terms, never a maximum over them: whatever the grace period,
    raising it must raise the allowance by the same amount, which a
    floor would not do for any value below the margin.
    """
    config_text = "\n".join(
        f'slow-timeout = {{ period = "1s", grace-period = "{value}{unit}" }}'
        for value, unit in periods
    )
    largest = max(value * UNITS[unit] for value, unit in periods)
    assert grace_period(config_text) == pytest.approx(largest), (
        "the largest configured grace period governs"
    )
    assert termination_allowance(config_text) == pytest.approx(
        largest + TERMINATION_SAFETY_MARGIN_SECONDS
    ), "the allowance is the grace period plus the margin, not the larger of them"


@given(text=st.text(max_size=40).filter(lambda body: "grace-period" not in body))
def test_an_unconfigured_grace_period_falls_back_to_nextest_s_default(
    text: str,
) -> None:
    """Text naming no grace period yields nextest's own ten seconds.

    Assuming zero instead would understate what nextest needs to stop a
    run, and the understatement would be invisible until a watchdog
    fired during the shutdown it had not budgeted for.
    """
    assert grace_period(text) == pytest.approx(NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS), (
        "an absent grace period must fall back to nextest's default"
    )


@pytest.mark.parametrize(
    "duration",
    ["", "300", "s", "300 sec", "five minutes", "-30s", "30d"],
    ids=[
        "empty",
        "no-unit",
        "no-value",
        "unknown-unit",
        "words",
        "negative",
        "days-are-not-a-nextest-unit",
    ],
)
def test_an_unreadable_duration_is_refused_rather_than_guessed(duration: str) -> None:
    """A duration nextest would reject must not become a number here.

    Returning a plausible value for `"30d"` would put a comparison in
    the contract against a budget nextest never applies, and the
    contract would pass while the ordering it claims to hold did not.
    """
    with pytest.raises(NextestConfigurationError):
        seconds(duration)


def test_a_slow_timeout_without_a_period_is_refused() -> None:
    """An entry naming only `terminate-after` has no budget to read.

    Treating the multiplier as the budget, or the entry as absent,
    would both understate the largest per-test allowance the whole-run
    budget has to sit above.
    """
    with pytest.raises(NextestConfigurationError):
        largest_test_allowance("slow-timeout = { terminate-after = 3 }")


def test_a_configuration_with_no_slow_timeout_is_refused() -> None:
    """There is no defensible largest budget when none is configured.

    Returning zero would make every whole-run budget look comfortably
    above the per-test allowance, which is the comparison this reading
    exists to support.
    """
    with pytest.raises(NextestConfigurationError):
        largest_test_allowance("[profile.default]\nfail-fast = false\n")
