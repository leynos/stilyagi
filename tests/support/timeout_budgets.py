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


#: A duration as ``humantime`` spells it: one or more whole-number
#: components, each carrying a unit, spaced or joined. nextest
#: deserializes every duration with ``humantime_serde``, so ``"1h 30m"``,
#: ``"1d"`` and ``"1w"`` are all configuration it accepts, and a
#: fractional value such as ``"1.5s"`` is one it refuses. A reader taking
#: a single component with a short unit rejects a file nextest would
#: load, and this contract would then blame the file for its own
#: limitation.
_DURATION: typ.Final[re.Pattern[str]] = re.compile(r"\A\s*(?:\d+\s*[A-Za-z]+\s*)+\Z")

#: One component of such a duration.
_COMPONENT: typ.Final[re.Pattern[str]] = re.compile(
    r"(?P<value>\d+)\s*(?P<unit>[A-Za-z]+)"
)

#: Every unit spelling ``humantime`` accepts, with its length in
#: seconds. Case is not folded: ``m`` is minutes and ``M`` is months, so
#: folding would read a thirty-minute budget as a two-and-a-half-year
#: one. A month is a twelfth of a Julian year and a year is 365.25 days,
#: which is how ``humantime`` defines them.
_UNIT_SECONDS: typ.Final[dict[str, float]] = {
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
        A duration as nextest spells it, such as ``"120s"`` or the
        multi-component ``"1h 30m"``.

    Returns
    -------
    float
        The duration in seconds.

    Raises
    ------
    NextestConfigurationError
        If the duration is not one nextest would accept.

    Examples
    --------
    >>> seconds("120s")
    120.0
    >>> seconds("1h 30m")
    5400.0
    """
    if _DURATION.match(duration) is None:
        msg = (
            f"unrecognized nextest duration {duration!r}; nextest reads "
            f"durations with humantime, which wants whole-number components "
            f'each carrying a unit, such as "120s" or "1h 30m"'
        )
        raise NextestConfigurationError(msg, field="duration", value=duration)
    total = 0.0
    for component in _COMPONENT.finditer(duration):
        unit = component["unit"]
        length = _UNIT_SECONDS.get(unit)
        if length is None:
            msg = (
                f"nextest duration {duration!r} names the unit {unit!r}, which "
                f"humantime does not accept; note that 'm' is minutes and 'M' "
                f"is months"
            )
            raise NextestConfigurationError(msg, field="duration", value=duration)
        total += float(component["value"]) * length
    return total


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
