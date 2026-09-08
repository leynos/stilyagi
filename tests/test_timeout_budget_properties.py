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

from tests.support.nextest_config import (
    grace_period,
    largest_test_allowance,
    termination_allowance,
)
from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    NextestConfigurationError,
    seconds,
)

#: Every unit spelling nextest accepts, with its length in seconds.
#: nextest deserializes durations with ``humantime_serde``, so this is
#: ``humantime``'s table, written out again rather than imported: the
#: unit table is the one place in the reading where a single wrong entry
#: would go unnoticed, because every comparison downstream would still
#: be an inequality between two plausible numbers. Case is significant,
#: ``m`` being minutes and ``M`` months.
UNITS: typ.Final[dict[str, float]] = {
    "nanos": 1e-9,
    "nsec": 1e-9,
    "ns": 1e-9,
    "usec": 1e-6,
    "us": 1e-6,
    "millis": 0.001,
    "msec": 0.001,
    "ms": 0.001,
    "seconds": 1.0,
    "second": 1.0,
    "secs": 1.0,
    "sec": 1.0,
    "s": 1.0,
    "minutes": 60.0,
    "minute": 60.0,
    "mins": 60.0,
    "min": 60.0,
    "m": 60.0,
    "hours": 3600.0,
    "hour": 3600.0,
    "hrs": 3600.0,
    "hr": 3600.0,
    "h": 3600.0,
    "days": 86400.0,
    "day": 86400.0,
    "d": 86400.0,
    "weeks": 604800.0,
    "week": 604800.0,
    "w": 604800.0,
    "months": 2630016.0,
    "month": 2630016.0,
    "M": 2630016.0,
    "years": 31557600.0,
    "year": 31557600.0,
    "y": 31557600.0,
}

whole_numbers = st.integers(min_value=1, max_value=10_000)
units = st.sampled_from(sorted(UNITS))
multipliers = st.integers(min_value=1, max_value=20)


def document(*tables: str, profile: str = "default") -> str:
    """Return a nextest document declaring those slow-timeouts.

    The reading parses the configuration, so one it is driven with has
    to be shaped the way nextest reads one: the first table is the
    profile's own and the rest are its overrides. A bare assignment at
    the root of the document is not configuration to nextest, and is not
    read as any here either.

    Parameters
    ----------
    *tables : str
        The ``slow-timeout`` assignments, profile's own first.
    profile : str
        The profile to declare them under.

    Returns
    -------
    str
        A configuration document.
    """
    lines = [f"[profile.{profile}]"]
    if tables:
        lines.append(tables[0])
    for override in tables[1:]:
        lines += ["", f"[[profile.{profile}.overrides]]", override]
    return "\n".join(lines) + "\n"


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
    config_text = document(
        *(
            f'slow-timeout = {{ period = "{value}{unit}", terminate-after = {times} }}'
            for value, unit, times in budgets
        )
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
    config_text = document(
        *(
            f'slow-timeout = {{ period = "1s", terminate-after = 1, '
            f'grace-period = "{value}{unit}" }}'
            for value, unit in periods
        )
    )
    largest = max(value * UNITS[unit] for value, unit in periods)
    assert grace_period(config_text) == pytest.approx(largest), (
        "the largest configured grace period governs"
    )
    assert termination_allowance(config_text) == pytest.approx(
        largest + TERMINATION_SAFETY_MARGIN_SECONDS
    ), "the allowance is the grace period plus the margin, not the larger of them"


@given(
    periods=st.lists(st.tuples(whole_numbers, units), min_size=1, max_size=6),
    profile=st.sampled_from(["default", "ci"]),
)
def test_an_unconfigured_grace_period_falls_back_to_nextest_s_default(
    periods: list[tuple[int, str]], profile: str
) -> None:
    """A configuration naming no grace period yields nextest's ten seconds.

    Assuming zero instead would understate what nextest needs to stop a
    run, and the understatement would be invisible until a watchdog
    fired during the shutdown it had not budgeted for.
    """
    config_text = document(
        *(
            f'slow-timeout = {{ period = "{value}{unit}", terminate-after = 1 }}'
            for value, unit in periods
        ),
        profile=profile,
    )
    assert grace_period(config_text) == pytest.approx(
        NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS
    ), "an absent grace period must fall back to nextest's default"


@pytest.mark.parametrize(
    "duration",
    ["", "300", "s", "five minutes", "-30s", "1.5s", "30 fortnights"],
    ids=[
        "empty",
        "no-unit",
        "no-value",
        "words",
        "negative",
        "fractional",
        "unknown-unit",
    ],
)
def test_an_unreadable_duration_is_refused_rather_than_guessed(duration: str) -> None:
    """A duration nextest would reject must not become a number here.

    Returning a plausible value for `"30 fortnights"` would put a
    comparison in the contract against a budget nextest never applies,
    and the contract would pass while the ordering it claims to hold did
    not. `humantime` takes whole numbers with units and nothing else, so
    a fractional value belongs here too.
    """
    with pytest.raises(NextestConfigurationError):
        seconds(duration)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        pytest.param("1h 30m", 5400.0, id="two-components-spaced"),
        pytest.param("1h30m", 5400.0, id="two-components-joined"),
        pytest.param("1d", 86400.0, id="a-day"),
        pytest.param("1w", 604800.0, id="a-week"),
        pytest.param("300 sec", 300.0, id="a-long-unit-spelling"),
    ],
)
def test_a_duration_nextest_accepts_is_read_rather_than_refused(
    duration: str, expected: float
) -> None:
    """`humantime` takes several components and long unit spellings.

    A reader taking one component with a short unit refuses `"1h 30m"`,
    `"1d"` and `"1w"`, which nextest loads without complaint. The
    contract then fails on a configuration that is correct, and the
    failure names the file rather than the reader that could not read
    it. These are the spellings a person is most likely to reach for
    when the file is finally written.
    """
    assert seconds(duration) == pytest.approx(expected), (
        f"{duration!r} is configuration nextest accepts"
    )


@given(first=whole_numbers, second=whole_numbers)
def test_the_components_of_a_duration_are_added(first: int, second: int) -> None:
    """A multi-component duration is the sum of its components.

    Written as a property because a reader that took only the first
    component, or only the last, would agree with a correct one on every
    single-component duration, which is every duration anybody has
    written here so far.
    """
    assert seconds(f"{first}h {second}m") == pytest.approx(
        first * 3600.0 + second * 60.0
    ), "each component contributes its own number of seconds"


def test_a_slow_timeout_without_a_period_is_refused() -> None:
    """An entry naming only `terminate-after` has no budget to read.

    Treating the multiplier as the budget, or the entry as absent,
    would both understate the largest per-test allowance the whole-run
    budget has to sit above.
    """
    with pytest.raises(NextestConfigurationError):
        largest_test_allowance(document("slow-timeout = { terminate-after = 3 }"))


def test_a_configuration_with_no_slow_timeout_is_refused() -> None:
    """There is no defensible largest budget when none is configured.

    Returning zero would make every whole-run budget look comfortably
    above the per-test allowance, which is the comparison this reading
    exists to support.
    """
    with pytest.raises(NextestConfigurationError):
        largest_test_allowance("[profile.default]\nfail-fast = false\n")
