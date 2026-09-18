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
from fractions import Fraction
from itertools import starmap

from tests.support.nextest_slow_timeouts import _budget_of, _slow_timeout_table
from tests.support.timeout_budgets import (
    NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS,
    TERMINATION_SAFETY_MARGIN_SECONDS,
    NextestConfigurationError,
    _duration,
    exact_seconds,
)


def _table(path: str, value: object) -> dict[str, object]:
    """Return a parsed value as a table, refusing one of another shape.

    Absent and malformed are different answers and were the same one.
    Reading ``overrides = "invalid"`` as an empty list, or a profile
    written as a string as an empty table, drops the tables a budget
    lives in and leaves the reading to report whatever remains: a
    profile keeping a valid ``slow-timeout`` beside a malformed
    ``overrides`` reported the profile's own budget as the largest, and
    nothing said the overrides had not been read. nextest refuses such a
    file outright, so a contract deriving a budget from it certifies a
    configuration that cannot run.

    Missing stays missing; the callers below decide what that means.

    Parameters
    ----------
    path : str
        The dotted path of the value, for the message.
    value : object
        Any value ``tomllib`` produced.

    Returns
    -------
    dict[str, object]
        The table.

    Raises
    ------
    NextestConfigurationError
        If the value is present and is not a table.
    """
    match value:
        case None:
            return {}
        case dict():
            return dict(value)
        case _:
            message = (
                f"{path} is {value!r}, which is not a table; nextest refuses "
                f"the file, so no budget can be read from it"
            )
            raise NextestConfigurationError(message, field=path, value=value)


def _entries(path: str, value: object) -> list[object]:
    """Return an ``overrides`` value as a list, refusing another shape.

    nextest defines ``overrides`` as an array of tables. Anything else
    was silently read as no overrides at all, which is the dangerous
    direction: the per-test allowances those entries carry vanish from
    the reading and the whole-run ceiling is approved against the
    profile's base timeout alone.

    Parameters
    ----------
    path : str
        The dotted path of the value, for the message.
    value : object
        Any value ``tomllib`` produced.

    Returns
    -------
    list of object
        The entries.

    Raises
    ------
    NextestConfigurationError
        If the value is present and is not a list.
    """
    match value:
        case None:
            return []
        case list():
            return list(value)
        case _:
            message = (
                f"{path} is {value!r}, which is not an array of tables; "
                f"nextest refuses the file, so no budget can be read from it"
            )
            raise NextestConfigurationError(message, field=path, value=value)


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
    declared = _table("profile", _parsed(config_text).get("profile"))
    for name, raw in declared.items():
        profile = _table(f"profile.{name}", raw)
        tables.append((f"profile.{name}", profile))
        entries = _entries(f"profile.{name}.overrides", profile.get("overrides"))
        tables.extend(
            (
                f"profile.{name}.overrides[{index}]",
                _table(f"profile.{name}.overrides[{index}]", entry),
            )
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


def largest_test_allowance(config_text: str) -> Fraction:
    """Return the longest a single test may run, in seconds.

    nextest warns once per ``period`` and terminates after
    ``terminate-after`` of them, so the budget is their product.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    Fraction
        The longest per-test budget, in seconds and exactly. See
        :func:`exact_seconds` for why this reading does not collapse to
        a ``float``.

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


def grace_period(config_text: str) -> Fraction:
    """Return the longest grace period the configuration names, in seconds.

    A ``grace-period`` that is present but is not a duration string is
    refused by :func:`_duration` rather than read as absent, so
    ``grace-period = 0`` is an error and not a silent fall back to
    nextest's ten-second default.

    The ``slow-timeout`` carrying it is validated first, through the
    same :func:`_slow_timeout_table` the budget derivation uses.
    Filtering non-tables out instead let a whole malformed declaration
    read as absent: ``slow-timeout = 0``, or a table whose ``period``
    nextest will not read, contributed nothing and left
    :func:`termination_allowance` returning the default. The budget
    derivation refused those same forms, so the two readings of one
    field disagreed, and in the dangerous direction.

    Parameters
    ----------
    config_text : str
        A nextest configuration's text.

    Returns
    -------
    Fraction
        The largest configured grace period, or nextest's default, in
        seconds and exactly.
    """
    periods = [
        exact_seconds(_duration(f"{path}.slow-timeout", "grace-period", grace))
        for path, value in _slow_timeouts(config_text)
        if (table := _slow_timeout_table(path, value)) is not None
        and (grace := table.get("grace-period")) is not None
    ]
    return max(periods, default=Fraction(NEXTEST_DEFAULT_GRACE_PERIOD_SECONDS))


def global_timeout(config_text: str) -> Fraction | None:
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
    Fraction or None
        The whole-run budget in seconds and exactly, or None when the
        profile names none. A value that is present but is not a duration string is
        refused by :func:`_duration` rather than read as absent.
    """
    profile = _table(
        "profile.default",
        _table("profile", _parsed(config_text).get("profile")).get("default"),
    )
    if "global-timeout" not in profile:
        return None
    return exact_seconds(
        _duration("profile.default", "global-timeout", profile["global-timeout"])
    )


def termination_allowance(config_text: str) -> Fraction:
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
    Fraction
        The grace period plus the safety margin, in seconds and
        exactly. The margin is a ``float`` constant and is converted
        rather than added, because mixing the two would round the sum
        and undo the exactness the grace period was read with.
    """
    return grace_period(config_text) + Fraction(TERMINATION_SAFETY_MARGIN_SECONDS)
