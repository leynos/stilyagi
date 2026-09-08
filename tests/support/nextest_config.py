"""Reading a nextest configuration as the runner reads it.

Separated from ``timeout_budgets`` so the parsing and the terms it feeds
stay legible apart, and so neither module outgrows the 400-line limit
the lint gate enforces.

The configuration is parsed with ``tomllib`` rather than matched as
text. A text match finds a key inside a comment, inside a ``filter``
string, or in a table nextest never consults, and reports a budget the
runner does not use.
"""

import tomllib
import typing as typ
from itertools import starmap

from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    NextestConfigurationError,
    UnboundedTestError,
    _duration,
    _multiplier,
    seconds,
)


def _table(value: object) -> dict[str, object]:
    """Return a parsed value as a table, or an empty one.

    Parameters
    ----------
    value : object
        Any value ``tomllib`` produced.

    Returns
    -------
    dict[str, object]
        The table, or an empty one when the value is not a table.
    """
    return dict(value) if isinstance(value, dict) else {}


def _parsed(config_text: str) -> dict[str, object]:
    """Return the nextest configuration as TOML.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text, empty when there is no file.

    Returns
    -------
    dict[str, object]
        The parsed document, empty when the text is.

    Raises
    ------
    NextestConfigurationError
        If the text is not valid TOML.
    """
    try:
        return tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as error:
        message = f"the nextest configuration is not valid TOML: {error}"
        raise NextestConfigurationError(
            message, field="config", value=config_text
        ) from error


def _budget_tables(config_text: str) -> list[tuple[str, dict[str, object]]]:
    """Return every table nextest reads a per-test budget from.

    Each profile's own table and each of its ``[[overrides]]`` entries,
    with the dotted path that names it so a failure can say which one is
    at fault.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    list of tuple
        The dotted path and the table, in file order.
    """
    tables: list[tuple[str, dict[str, object]]] = []
    for name, raw in _table(_parsed(config_text).get("profile")).items():
        profile = _table(raw)
        tables.append((f"profile.{name}", profile))
        overrides = profile.get("overrides")
        entries = overrides if isinstance(overrides, list) else []
        tables.extend(
            (f"profile.{name}.overrides[{index}]", _table(entry))
            for index, entry in enumerate(entries)
        )
    return tables


def _slow_timeouts(config_text: str) -> list[tuple[str, object]]:
    """Return every ``slow-timeout`` the configuration declares.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    list of tuple
        The dotted path of the declaring table and the value.
    """
    return [
        (path, table["slow-timeout"])
        for path, table in _budget_tables(config_text)
        if "slow-timeout" in table
    ]


def largest_test_allowance(config_text: str) -> float:
    """Return the longest a single test may run, in seconds.

    nextest warns once per ``period`` and terminates after
    ``terminate-after`` of them, so the budget is their product.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    float
        The longest per-test budget.

    A ``slow-timeout`` that terminates nothing raises
    :class:`UnboundedTestError` from :func:`_budget_of`, because such a
    configuration bounds no test at all.

    Raises
    ------
    NextestConfigurationError
        If the configuration declares no ``slow-timeout`` at all.
    """
    budgets = list(starmap(_budget_of, _slow_timeouts(config_text)))
    if not budgets:
        message = (
            "the nextest configuration declares no slow-timeout, so no test "
            "is bounded and there is no per-test tier to compare against"
        )
        raise NextestConfigurationError(
            message, field="slow-timeout", value=config_text
        )
    return max(budgets)


def _budget_of(path: str, value: object) -> float:
    """Return the per-test budget one ``slow-timeout`` declares.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    value : object
        The parsed value, a table or a bare duration.

    Returns
    -------
    float
        The budget in seconds.

    A value that names no ``terminate-after``, in either spelling,
    raises :class:`UnboundedTestError` from the helper that reads it.

    Raises
    ------
    NextestConfigurationError
        If the value is neither a table nor a duration.
    """
    match value:
        case str():
            return _bare_budget(path, value)
        case dict():
            return _table_budget(path, value)
        case _:
            message = f"{path}.slow-timeout is neither a table nor a duration"
            raise NextestConfigurationError(message, field="slow-timeout", value=value)


def _table_budget(path: str, table: dict[str, object]) -> float:
    """Return one inline ``slow-timeout`` table's per-test budget.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    table : dict[str, object]
        The parsed table.

    Returns
    -------
    float
        The period multiplied by ``terminate-after``, in seconds.

    Raises
    ------
    NextestConfigurationError
        If the table names no ``period``, or names a ``terminate-after``
        that is not a positive integer.
    UnboundedTestError
        If the table names no ``terminate-after``, so nextest warns
        about a slow test forever and never stops it.
    """
    period = table.get("period")
    if not isinstance(period, str):
        message = f"{path}.slow-timeout names no period: {table!r}"
        raise NextestConfigurationError(message, field="period", value=table)
    multiplier = table.get("terminate-after")
    if multiplier is None:
        message = (
            f"{path}.slow-timeout sets no terminate-after, so nextest marks "
            f"the test slow and lets it run on; there is no per-test tier to "
            f"compare against"
        )
        raise UnboundedTestError(message, field="terminate-after", value=table)
    return seconds(period) * _multiplier(path, multiplier)


def _bare_budget(path: str, period: str) -> typ.NoReturn:
    """Refuse a ``slow-timeout`` written as a bare duration.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    period : str
        The duration the configuration named.

    Raises
    ------
    UnboundedTestError
        Always. The bare form sets a warning period with no
        ``terminate-after``, so no test is ever terminated by it.
    """
    message = (
        f'{path}.slow-timeout = "{period}" sets a warning period with no '
        f"terminate-after, so nextest reports the test as slow and never "
        f"stops it; there is no per-test tier to compare against"
    )
    raise UnboundedTestError(message, field="slow-timeout", value=period)


def grace_period(config_text: str) -> float:
    """Return the longest grace period the configuration names, in seconds.

    A ``grace-period`` that is present but is not a duration string is
    refused by :func:`_duration` rather than read as absent, so
    ``grace-period = 0`` is an error and not a silent fall back to
    nextest's ten-second default.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    float
        The largest configured grace period, or nextest's default.
    """
    periods = [
        seconds(_duration(f"{path}.slow-timeout", "grace-period", grace))
        for path, value in _slow_timeouts(config_text)
        if isinstance(value, dict) and (grace := value.get("grace-period")) is not None
    ]
    return max(periods, default=NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS)


def global_timeout(config_text: str) -> float | None:
    """Return the whole-run budget, or None when none is set.

    Read from ``[profile.default]`` alone. nextest's other profiles
    inherit that table unless they override it, and an ``[[overrides]]``
    entry cannot carry one.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    float or None
        The whole-run budget in seconds, or None when the profile names
        none. A value that is present but is not a duration string is
        refused by :func:`_duration` rather than read as absent.
    """
    profile = _table(_table(_parsed(config_text).get("profile")).get("default"))
    if "global-timeout" not in profile:
        return None
    return seconds(
        _duration("profile.default", "global-timeout", profile["global-timeout"])
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
