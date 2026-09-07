"""Pure readings of a nextest configuration's timeout budgets.

Separated from `tests/test_timeout_ordering_contract.py` so the
arithmetic can be exercised against controlled configurations without
the workflow reading around it. This repository has no
`.config/nextest.toml`, so every reading here is driven by strings the
tests supply.
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
_SLOW_TIMEOUT: typ.Final[re.Pattern[str]] = re.compile(
    r"slow-timeout\s*=\s*\{(?P<body>[^}]*)\}"
)

#: A ``slow-timeout`` given as a bare duration rather than a table.
#: nextest accepts this form and it never terminates a test.
_BARE_SLOW_TIMEOUT: typ.Final[re.Pattern[str]] = re.compile(
    r'slow-timeout\s*=\s*"([^"]+)"'
)

_GRACE_PERIOD: typ.Final[re.Pattern[str]] = re.compile(r'grace-period\s*=\s*"([^"]+)"')


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


def largest_test_allowance(config_text: str) -> float:
    """Return the longest a single test may run, in seconds.

    Parameters
    ----------
    config_text : str
        The nextest configuration file's text.

    Returns
    -------
    float
        The longest per-test budget, period multiplied by
        ``terminate-after``.

    Raises
    ------
    NextestConfigurationError
        If a ``slow-timeout`` names no period, or none is set at all.
    """
    budgets = [
        _table_budget(match["body"]) for match in _SLOW_TIMEOUT.finditer(config_text)
    ]
    budgets.extend(
        _bare_budget(value) for value in _BARE_SLOW_TIMEOUT.findall(config_text)
    )
    if not budgets:
        msg = "nextest.toml must set at least one slow-timeout"
        raise NextestConfigurationError(msg, field="slow-timeout", value=None)
    return max(budgets)


def _table_budget(body: str) -> float:
    """Return one inline ``slow-timeout`` table's per-test budget.

    Parameters
    ----------
    body : str
        The table's contents, without its braces.

    Returns
    -------
    float
        ``period`` multiplied by ``terminate-after``.

    Raises
    ------
    NextestConfigurationError
        If the table names no period.
    UnboundedTestError
        If it names no ``terminate-after``, so nextest never terminates
        a test that exceeds the period.
    """
    period = re.search(r'period\s*=\s*"([^"]+)"', body)
    if period is None:
        msg = f"slow-timeout without a period: {body!r}"
        raise NextestConfigurationError(msg, field="slow-timeout", value=body)
    terminate = re.search(r"terminate-after\s*=\s*(\d+)", body)
    if terminate is None:
        msg = (
            f"slow-timeout {body!r} sets no terminate-after, so nextest marks "
            f"a test slow and never ends it; the per-test tier is absent"
        )
        raise UnboundedTestError(msg, field="terminate-after", value=None)
    return seconds(period[1]) * int(terminate[1])


def _bare_budget(value: str) -> typ.NoReturn:
    """Return the budget a bare ``slow-timeout = "2m"`` gives.

    Parameters
    ----------
    value : str
        The duration the setting names.

    Raises
    ------
    UnboundedTestError
        Always. The string form takes no ``terminate-after``, so nextest
        marks a test slow after the period and lets it run for ever.
    """
    msg = (
        f"slow-timeout = {value!r} is the warn-only form: nextest marks a "
        f"test slow after {value} and never ends it, so the per-test tier is "
        f"absent. Use a table with terminate-after to bound a test"
    )
    raise UnboundedTestError(msg, field="slow-timeout", value=value)


def grace_period(config_text: str) -> float:
    """Return the longest grace period the configuration names, in seconds.

    Read from the configuration rather than fixed, so a profile that
    raised its grace period raises the requirement too. nextest's own
    ten-second default applies when none is named, as none is here.

    Parameters
    ----------
    config_text : str
        The nextest configuration file's text.

    Returns
    -------
    float
        The largest configured grace period, or nextest's default.
    """
    periods = _GRACE_PERIOD.findall(config_text)
    return max(
        (seconds(period) for period in periods),
        default=NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    )


def termination_allowance(config_text: str) -> float:
    """Return the time nextest may take to stop the run, in seconds.

    Two terms, not one: what nextest promises a test after ``SIGTERM``,
    plus a margin for the teardown and report writing that follow it.
    A single floor over the two would make a raised grace period look
    free right up to the run it cancelled.

    Parameters
    ----------
    config_text : str
        The nextest configuration file's text.

    Returns
    -------
    float
        The grace period plus the safety margin.
    """
    return grace_period(config_text) + TERMINATION_SAFETY_MARGIN_SECONDS


def global_timeout(config_text: str) -> float | None:
    """Return the whole-run budget, or None when none is set.

    Parameters
    ----------
    config_text : str
        The nextest configuration file's text.

    Returns
    -------
    float or None
        The whole-run budget in seconds, or None.
    """
    match = re.search(r'^global-timeout\s*=\s*"([^"]+)"', config_text, re.MULTILINE)
    return None if match is None else seconds(match[1])
