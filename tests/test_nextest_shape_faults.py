"""What the nextest reading does with a shape it cannot read.

Separated from `test_timeout_readings`, whose subject is what the
readings compute from configurations they can read, and so neither
module outgrows the 400-line limit the lint gate enforces.

The subject here is the other answer: a value that is present and of the
wrong shape. nextest refuses such a file outright, so a budget derived
from one describes a configuration that cannot run, and reading it as
absent is the silent way to get that wrong.
"""

import typing as typ

import pytest

from tests.support.nextest_config import (
    grace_period,
    largest_test_allowance,
    termination_allowance,
)
from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    NextestConfigurationError,
)


@pytest.mark.parametrize(
    ("config_text", "field"),
    [
        pytest.param(
            'profile = "invalid"\n',
            "profile",
            id="a-profile-table-that-is-not-a-table",
        ),
        pytest.param(
            'profile.default = "invalid"\n',
            "profile.default",
            id="a-profile-that-is-not-a-table",
        ),
        pytest.param(
            "[profile.default]\n"
            'slow-timeout = { period = "300s", terminate-after = 1 }\n'
            'overrides = "invalid"\n',
            "profile.default.overrides",
            id="overrides-that-are-not-an-array",
        ),
        pytest.param(
            "[profile.default]\n"
            'slow-timeout = { period = "300s", terminate-after = 1 }\n'
            'overrides = ["invalid"]\n',
            "profile.default.overrides[0]",
            id="an-override-entry-that-is-not-a-table",
        ),
    ],
)
def test_a_malformed_shape_is_refused_rather_than_read_as_absent(
    config_text: str, field: str
) -> None:
    """Present and malformed is not the same answer as absent.

    nextest defines `overrides` as an array of tables and refuses a file
    that says otherwise, so no budget should be derived from one. The
    third case is the dangerous one and the reason the distinction
    matters: the profile carries a perfectly good `slow-timeout` beside
    a malformed `overrides`, so a reading that treated the malformed
    value as no overrides at all returned the profile's own budget as
    the largest, with nothing saying the overrides had not been read.
    The whole-run ceiling would then be approved against a per-test
    allowance the runner never saw.

    The declaring path is asserted rather than the exception type alone.
    Two of these cases raise a `NextestConfigurationError` either way:
    with the shapes read as empty there is then no `slow-timeout` in the
    document at all, and the reading refuses it for that instead. A test
    that only caught the type passed on the mutation that defeated it.
    """
    with pytest.raises(NextestConfigurationError) as raised:
        largest_test_allowance(config_text)
    assert raised.value.field == field, (
        f"the refusal must be attributed to {field}, the value that is "
        f"malformed, and names {raised.value.field!r}"
    )


def test_an_absent_overrides_key_still_reads_as_no_overrides() -> None:
    """Assert the refusal above is narrow as well as sufficient.

    A reader that refused every shape would pass every case in the table
    and reject the configurations this repository writes, so the absent
    case is pinned beside the malformed ones: a profile with no
    `overrides` key at all is not malformed, it simply has none.
    """
    config_text = (
        '[profile.default]\nslow-timeout = { period = "300s", terminate-after = 2 }\n'
    )
    assert largest_test_allowance(config_text) == pytest.approx(600.0), (
        "a profile declaring no overrides reads as its own budget"
    )


@pytest.mark.parametrize(
    ("config_text", "field", "value"),
    [
        pytest.param(
            "[profile.default]\nslow-timeout = 0\n",
            "slow-timeout",
            0,
            id="a-slow-timeout-that-is-neither-a-table-nor-a-duration",
        ),
        pytest.param(
            "[profile.default]\nslow-timeout = { period = 0, terminate-after = 1 }\n",
            "period",
            0,
            id="a-period-that-is-present-and-not-a-duration",
        ),
    ],
)
def test_the_grace_period_reading_refuses_what_the_budget_reading_refuses(
    config_text: str, field: str, value: object
) -> None:
    """Two readings of one field must not disagree about what it says.

    `grace_period` filtered its input instead of validating it: it kept
    tables and dropped everything else, then kept tables carrying a
    `grace-period` and dropped the rest. So a `slow-timeout = 0`, and a
    table whose `period` nextest will not read, both contributed nothing
    and `termination_allowance` returned the ten-second default. The
    budget derivation refused those same two forms.

    That is the dangerous direction rather than the safe one. The
    reading that refuses is the one nobody acts on; the reading that
    returns a default puts a number on the termination tier for a file
    the runner will not load, and the ordering contract then approves a
    watchdog against it.

    The declaring field and the offending value are both asserted. With
    the shapes filtered out there is no `slow-timeout` left in the
    document, so a reading can raise the same exception type for a
    different reason entirely, and a test that only caught the type
    would pass on the mutation that defeats it.
    """
    with pytest.raises(NextestConfigurationError) as raised:
        grace_period(config_text)
    assert (raised.value.field, raised.value.value) == (field, value), (
        f"the refusal must name {field!r} and the value {value!r}; it named "
        f"{raised.value.field!r} and {raised.value.value!r}"
    )


def test_a_missing_period_is_reported_apart_from_a_malformed_one() -> None:
    """Absent and present-but-wrong are different faults.

    Both were reported as "names no period" with the whole table as the
    value, so a reader of the failure could not tell whether a key was
    missing or written as something nextest will not read, and the
    structured `value` pointed at the table rather than at the thing to
    change.
    """
    with pytest.raises(NextestConfigurationError) as raised:
        largest_test_allowance(
            "[profile.default]\nslow-timeout = { terminate-after = 1 }\n"
        )
    assert raised.value.field == "period", "the absent key is still a period fault"
    assert raised.value.value == {"terminate-after": 1}, (
        "an absent key has no value of its own, so the table is what the "
        "failure can point at"
    )


def test_a_well_formed_slow_timeout_without_a_grace_period_keeps_the_default() -> None:
    """Assert the refusals above are narrow as well as sufficient.

    A `grace_period` that refused every form it could not collect a
    period from would satisfy both cases above and reject the
    configuration this repository writes, where no `grace-period` is
    named at all. Validating a form is not the same as requiring a key
    inside it.

    The bare duration form is here for the same reason. It is malformed
    only as a budget, because it bounds no test, and that is the budget
    reading's judgement to make rather than this one's; it carries no
    grace period either way.
    """
    bounded = (
        '[profile.default]\nslow-timeout = { period = "300s", terminate-after = 1 }\n'
    )
    bare = '[profile.default]\nslow-timeout = "300s"\n'
    for config_text in (bounded, bare):
        assert grace_period(config_text) == NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS, (
            f"a well-formed slow-timeout naming no grace-period keeps "
            f"nextest's default: {config_text!r}"
        )
        assert termination_allowance(config_text) == (
            NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS + TERMINATION_SAFETY_MARGIN_SECONDS
        ), f"and the allowance built on it: {config_text!r}"


@pytest.mark.parametrize(
    "reading",
    [
        pytest.param(grace_period, id="grace-period"),
        pytest.param(largest_test_allowance, id="budget"),
    ],
)
def test_a_malformed_bare_duration_is_a_configuration_fault(
    reading: typ.Callable[[str], object],
) -> None:
    """A bare `slow-timeout` nextest cannot parse is malformed, not unbounded.

    The bare form was answered before its text was read, so the budget
    reading called `"not-a-duration"` an unbounded test and the grace
    period reading skipped it and returned nextest's default. Both
    describe a configuration the runner will not load as one it will.
    """
    config_text = '[profile.default]\nslow-timeout = "not-a-duration"\n'
    with pytest.raises(NextestConfigurationError) as raised:
        reading(config_text)
    assert raised.value.value == "not-a-duration", (
        f"the refusal must name the malformed duration; it named "
        f"{raised.value.value!r}"
    )
