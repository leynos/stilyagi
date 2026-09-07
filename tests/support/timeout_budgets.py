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

import re
import typing as typ

#: What nextest allows a test between `SIGTERM` and `SIGKILL` when the
#: configuration names no `grace-period`.
NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS: typ.Final[float] = 10.0

#: Added to that grace period to cover the teardown and report writing
#: that follow it. Kept a separate term rather than folded into a single
#: floor, so raising the grace period raises the requirement instead of
#: being absorbed silently.
TERMINATION_SAFETY_MARGIN_SECONDS: typ.Final[float] = 60.0


class TimeoutBudgetError(ValueError):
    """Base for every fault these readings report.

    Callers catch this rather than matching message text, and the two
    fields carry what a caller would otherwise have to parse out of the
    message: which setting was at fault and what it held.

    Attributes
    ----------
    field : str
        The configuration key the fault is about.
    value : object
        What that key held, as the configuration gave it.
    """

    def __init__(self, message: str, *, field: str, value: object) -> None:
        """Record the message and the setting it is about.

        Parameters
        ----------
        message : str
            What went wrong, for a person reading the failure.
        field : str
            The configuration key the fault is about.
        value : object
            What that key held.
        """
        super().__init__(message)
        self.field = field
        self.value = value


class NextestConfigurationError(TimeoutBudgetError):
    """Raised when a nextest configuration cannot be read as written.

    A malformed duration or a `slow-timeout` without a period would
    otherwise be read as some plausible number, and the ordering above
    it would be checked against a value nextest never uses.
    """


class UnboundedTestError(TimeoutBudgetError):
    """Raised when a ``slow-timeout`` bounds nothing.

    ``terminate-after`` is optional, and nextest only terminates a test
    when it is set: `slow-timeout = "2m"` and
    `slow-timeout = { period = "2m" }` both mark a test slow after two
    minutes and then let it run for ever. Reading either as a two-minute
    budget reports tier one as present when it is absent, which is the
    inversion this contract exists to catch.
    """


_DURATION: typ.Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h)\s*$"
)

_UNIT_SECONDS: typ.Final[dict[str, float]] = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}


#: One `slow-timeout` inline table, captured whole so the period and the
#: multiplier that scales it are read together. nextest warns once per
#: `period` and terminates after `terminate-after` of them, so the budget
#: is their product; reading the period alone understates it fivefold
#: here.
def seconds(duration: str) -> float:
    """Convert a nextest duration to seconds.

    Parameters
    ----------
    duration : str
        A duration as nextest spells it, such as ``"120s"``.

    Returns
    -------
    float
        The duration in seconds.

    Raises
    ------
    NextestConfigurationError
        If the duration is not one nextest would accept.
    """
    match = _DURATION.match(duration)
    if match is None:
        msg = f"unrecognized nextest duration {duration!r}"
        raise NextestConfigurationError(msg, field="duration", value=duration)
    return float(match["value"]) * _UNIT_SECONDS[match["unit"]]
