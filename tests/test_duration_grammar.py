"""The duration grammar, against the one humantime reads.

Split from `test_timeout_budget_properties` so neither module outgrows
the 400-line limit `AGENTS.md` sets. The budget arithmetic is asserted
there; what a duration *is* is asserted here.

Every spelling was measured against humantime 2.3.0, which is what the
lockfile of the pinned cargo-nextest release resolves, by compiling that
parser and running the cases through it.
"""

import pytest
from hypothesis import given

from tests.support.nextest_units import HumantimeOverflowError
from tests.support.timeout_budgets import NextestConfigurationError, seconds
from tests.test_timeout_budget_properties import (
    UNITS,
    fractional_parts,
    fractional_units,
    units,
    whole_numbers,
)


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


@given(whole=whole_numbers, fraction=fractional_parts, unit=fractional_units)
def test_a_fractional_value_scales_its_unit(
    whole: int, fraction: int, unit: str
) -> None:
    """A fractional value scales by its unit, as humantime reads it.

    An earlier reader took whole numbers only, so `"1.5m"` was refused
    as malformed. nextest loads it as ninety seconds, and a contract
    that refuses configuration the runner accepts fails a correct file
    and blames the file for it. Written as a property because the defect
    was in the grammar rather than in any one spelling.

    The units are those a three-digit fraction can be written against.
    humantime counts in whole nanoseconds, so a fraction of a nanosecond
    is not a duration at all and is asserted as a refusal instead.
    """
    written = f"{whole}.{fraction}"
    assert seconds(f"{written}{unit}") == pytest.approx(float(written) * UNITS[unit]), (
        f"{written}{unit} must scale its fractional value by the unit"
    )


@pytest.mark.parametrize(
    "duration",
    [
        "",
        "300",
        "s",
        "five minutes",
        "-30s",
        ".5s",
        "5.s",
        "1.5.5s",
        "1S",
        "00",
        " 0 ",
        "0 ",
        "0.0000000002s",
        "0.0000000015s",
        "0.5ns",
        "18446744073709551616s",
        "1000000000000000000000ns",
        "18446744073709551615s 1s",
        "18446744073709551615s 500ms 500ms",
        "\u0663\u0660\u0660s",
        "3\u0660\u0660s",
        "0.0000000004s 0.0000000006s",
        "1.0ns",
        "2.0ns",
        "0.000001h",
        "0.1000000000000000000s",
        "1.00000000000000000000s",
        "30 fortnights",
    ],
    ids=[
        "empty",
        "no-unit",
        "no-value",
        "words",
        "negative",
        "only-a-fractional-part",
        "a-missing-fractional-part",
        "a-second-point",
        "a-unit-whose-case-is-wrong",
        "a-zero-that-is-not-the-bare-one",
        "a-bare-zero-carrying-whitespace",
        "a-bare-zero-with-a-trailing-space",
        "below-one-nanosecond",
        "a-fraction-of-a-nanosecond",
        "half-a-nanosecond",
        "one-second-past-the-u64-humantime-accumulates-into",
        "a-literal-past-the-u64-humantime-reads-it-into",
        "a-sum-past-the-u64-humantime-accumulates-into",
        "a-carry-that-completes-a-second-past-the-u64",
        "a-run-of-unicode-digits",
        "a-unicode-digit-after-an-ascii-one",
        "components-that-are-whole-only-together",
        "a-whole-fraction-of-a-nanosecond",
        "a-larger-whole-fraction-of-a-nanosecond",
        "an-hour-fraction-that-is-not-whole-seconds",
        "a-fraction-whose-product-leaves-the-u64",
        "a-fraction-whose-denominator-leaves-the-u64",
        "unknown-unit",
    ],
)
def test_an_unreadable_duration_is_refused_rather_than_guessed(duration: str) -> None:
    r"""A duration nextest would reject must not become a number here.

    Returning a plausible value for `"30 fortnights"` would put a
    comparison in the contract against a budget nextest never applies,
    and the contract would pass while the ordering it claims to hold did
    not. `humantime` admits a fractional part but nothing looser, so a
    leading point, a missing fractional part, a second point, a sign and
    a unit in the wrong case belong here. Each spelling was refused by
    humantime 2.3.0, which is what the lockfile of the pinned
    cargo-nextest release resolves, when the cases were run through that
    parser. The bare zero is the sharpest: humantime special-cases the
    exact text before reading a character, so a reader that stripped
    whitespace before comparing would accept `" 0 "`, which nextest
    rejects.

    One case leaves the parser by a different door. Two half-seconds on
    top of the largest whole second reach exactly a billion nanoseconds,
    which humantime's carry declines to move and `Duration::new` then
    moves regardless, panicking on the overflow. humantime returns no
    error for that text because it never returns at all, so nextest
    cannot load it either way, and a reader carrying only past a
    complete second would report a duration for it. One nanosecond
    short of that carry is the largest duration humantime does hold,
    and it sits in the acceptance cases as the other half of the pair.

    The two runs of Unicode digits are the reader's own width rather
    than the parser's. Python's `\d` matches every Unicode decimal
    digit and `int` reads them, so both spellings were three hundred
    seconds here; humantime compares against `'0'..='9'` and refuses
    them, reporting "expected number at 0" for the run that opens with
    one and "invalid character at 1" for the run that does not. The
    mixed spelling is the sharper of the two, because a reader that
    checked only its first character would still accept it.
    """
    with pytest.raises(NextestConfigurationError):
        seconds(duration)


def test_a_refusal_names_the_arithmetic_that_produced_it() -> None:
    """The overflow that refused a component survives the translation.

    `NextestConfigurationError` says which configuration field is at
    fault; `HumantimeOverflowError` says which of humantime's checked
    operations declined. Suppressing the second leaves a reader of the
    traceback with the sentence about fractions and no way to tell a
    literal past the `u64` from a division with a remainder.
    """
    with pytest.raises(NextestConfigurationError) as refusal:
        seconds("1.0ns")
    assert isinstance(refusal.value.__cause__, HumantimeOverflowError), (
        "the parser failure is the cause of the refusal, not a detail to drop"
    )


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        pytest.param("1h 30m", 5400.0, id="two-components-spaced"),
        pytest.param("1h30m", 5400.0, id="two-components-joined"),
        pytest.param("1d", 86400.0, id="a-day"),
        pytest.param("1w", 604800.0, id="a-week"),
        pytest.param("300 sec", 300.0, id="a-long-unit-spelling"),
        pytest.param("1.5m", 90.0, id="a-fractional-value"),
        pytest.param("1 . 5 m", 90.0, id="a-fractional-value-spaced-around-the-point"),
        pytest.param("4.2s", 4.2, id="a-fractional-value-in-seconds"),
        pytest.param("2wk", 1209600.0, id="the-short-week-spelling"),
        pytest.param("2wks", 1209600.0, id="the-short-plural-week-spelling"),
        pytest.param("1yr", 31557600.0, id="the-short-year-spelling"),
        pytest.param("3yrs", 94672800.0, id="the-short-plural-year-spelling"),
        pytest.param("1\u00b5s", 1e-6, id="the-micro-sign-spelling"),
        pytest.param("0", 0.0, id="the-bare-zero-humantime-reads-without-a-unit"),
        pytest.param("1 0s", 10.0, id="whitespace-inside-the-number"),
        pytest.param("1 2 . 3 4 s", 12.34, id="whitespace-throughout-the-number"),
        pytest.param("1.999999999s", 1.999999999, id="nanosecond-precision"),
        pytest.param(
            "18446744073709551615s 999999999ns",
            18446744073709551615 + 0.999999999,
            id="the-largest-duration-humantime-holds",
        ),
        pytest.param("0.000001ms", 1e-9, id="a-fraction-that-lands-on-a-nanosecond"),
        pytest.param("0.25h", 900.0, id="a-fraction-of-an-hour-in-whole-seconds"),
        pytest.param("0.5m", 30.0, id="a-fraction-of-a-minute"),
        pytest.param("0.5y", 15778800.0, id="a-fraction-of-a-year"),
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
