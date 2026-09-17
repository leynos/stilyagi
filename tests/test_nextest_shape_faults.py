"""What the nextest reading does with a shape it cannot read.

Separated from `test_timeout_readings`, whose subject is what the
readings compute from configurations they can read, and so neither
module outgrows the 400-line limit the lint gate enforces.

The subject here is the other answer: a value that is present and of the
wrong shape. nextest refuses such a file outright, so a budget derived
from one describes a configuration that cannot run, and reading it as
absent is the silent way to get that wrong.
"""

import pytest

from tests.support.nextest_config import largest_test_allowance
from tests.support.timeout_budgets import NextestConfigurationError


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
