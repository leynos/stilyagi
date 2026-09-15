"""Pure readings of a nextest configuration's timeout budgets.

Separated from `tests/test_timeout_ordering_contract.py` so the
arithmetic can be exercised against controlled configurations without
the workflow reading around it. This repository has no
`.config/nextest.toml`, so every reading here is driven by strings the
tests supply.

The configuration is parsed with ``tomllib`` rather than matched as
text. A text match finds a key inside a comment, inside a ``filter``
string, or in a table nextest never consults, and reports a budget the
runner does not use. That matters here because the file does not exist
yet: whoever adds it will get the reading the runner would give, not
the reading a regular expression happens to give.
"""

import typing as typ

from tests.support.nextest_durations import seconds
from tests.support.nextest_errors import (
    NextestConfigurationError,
    TimeoutBudgetError,
    UnboundedTestError,
)

#: Re-exported so every module that reads a budget through this one
#: keeps a single import site for the faults it reports and for the
#: duration reading those faults come out of.
__all__ = [
    "NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS",
    "TERMINATION_SAFETY_MARGIN_SECONDS",
    "NextestConfigurationError",
    "TimeoutBudgetError",
    "UnboundedTestError",
    "seconds",
]

#: What nextest allows a test between `SIGTERM` and `SIGKILL` when the
#: configuration names no `grace-period`.
NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS: typ.Final[float] = 10.0

#: Added to that grace period to cover the teardown and report writing
#: that follow it. Kept a separate term rather than folded into a single
#: floor, so raising the grace period raises the requirement instead of
#: being absorbed silently.
TERMINATION_SAFETY_MARGIN_SECONDS: typ.Final[float] = 60.0


def _multiplier(path: str, declared: object) -> int:
    """Return one ``terminate-after`` as the count nextest reads.

    nextest deserializes the field as ``NonZeroUsize``, so a fraction, a
    zero, a negative, a quoted number and a boolean are each a
    configuration it refuses to load. Coercing them through ``float``
    instead produced a budget for values nextest never accepts, and
    raised ``ValueError`` out of the reading for the rest, which is not
    the error this contract reports faults with.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    declared : object
        The parsed value of ``terminate-after``.

    Returns
    -------
    int
        The number of periods after which nextest terminates the test.

    Raises
    ------
    NextestConfigurationError
        If the value is anything but a positive integer.
    """
    positive_integer = isinstance(declared, int) and not isinstance(declared, bool)
    if not positive_integer or declared < 1:
        message = (
            f"{path}.slow-timeout has terminate-after = {declared!r}; nextest "
            f"reads it as a non-zero unsigned integer, so this configuration "
            f"would not load and there is no per-test budget to read from it"
        )
        raise NextestConfigurationError(
            message, field="terminate-after", value=declared
        )
    return declared


def _duration(path: str, field: str, declared: object) -> str:
    """Return a present duration's text, refusing any other type.

    nextest spells every duration as a string. Filtering a present
    non-string out instead made the setting read as absent, so
    ``grace-period = 0`` selected nextest's ten-second default and
    ``global-timeout = 0`` read as no whole-run budget at all. Both put
    a number on the tiers that the configuration does not hold, and the
    zero is the shape a person would most plausibly write.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    field : str
        The key being read, for the message.
    declared : object
        The parsed value.

    Returns
    -------
    str
        The duration's text.

    Raises
    ------
    NextestConfigurationError
        If the value is present and is not a string.
    """
    if not isinstance(declared, str):
        message = (
            f"{path}.{field} = {declared!r} is not a duration; nextest spells "
            f'every duration as a string, so write "0s" rather than 0'
        )
        raise NextestConfigurationError(message, field=field, value=declared)
    return declared
