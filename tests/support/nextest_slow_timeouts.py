"""Reading one ``slow-timeout`` as nextest reads it.

Separated from ``nextest_config`` so the configuration's structure and
the grammar of a single declaration stay legible apart, and so neither
module outgrows the 400-line limit the lint gate enforces.
``nextest_config`` imports what it needs from here, so a caller reading
a budget still has one import rather than two.

``slow-timeout`` has two spellings and they are not interchangeable. A
table carries a ``period`` and may carry a ``terminate-after`` and a
``grace-period``; a bare duration carries a warning period and nothing
else, so nextest reports the test as slow and never stops it. Both are
valid configuration, and only one of them bounds a test.
"""

import typing as typ

from tests.support.timeout_budgets import (
    NextestConfigurationError,
    UnboundedTestError,
    _duration,
    _multiplier,
    exact_seconds,
)

if typ.TYPE_CHECKING:
    from fractions import Fraction


def _budget_of(path: str, value: object) -> Fraction:
    """Return the per-test budget one ``slow-timeout`` declares.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    value : object
        The parsed value, a table or a bare duration.

    Returns
    -------
    Fraction
        The budget in seconds, exactly. See :func:`exact_seconds` for
        why this reading does not collapse to a ``float``.

    A value that names no ``terminate-after``, in either spelling,
    raises :class:`UnboundedTestError` from the helper that reads it,
    and one that is neither a table nor a duration raises
    :class:`NextestConfigurationError` from :func:`_slow_timeout_table`.
    """
    table = _slow_timeout_table(path, value)
    if table is None:
        _bare_budget(path, typ.cast("str", value))
    return _table_budget(path, table)


def _slow_timeout_table(path: str, value: object) -> dict[str, object] | None:
    """Return a ``slow-timeout``'s validated table, or None for the bare form.

    The single place that decides what a well-formed ``slow-timeout``
    is. It was written because two readers of that one field disagreed:
    the budget derivation refused a ``slow-timeout = 0`` and a table
    whose ``period`` was malformed, while ``grace_period`` filtered both
    out and read them as absent, so ``termination_allowance`` returned
    nextest's default for a configuration the runner will not load. Two
    readings of one field must not disagree, least of all in the
    direction that reports a budget for a file that cannot run.

    The bare duration form is answered with None rather than refused
    here. It is malformed only as a *budget*, because it names no
    ``terminate-after``, and that is :func:`_bare_budget`'s judgement to
    make. It carries no grace period either way, so ``grace_period``
    skips it.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    value : object
        The parsed ``slow-timeout``.

    Returns
    -------
    dict or None
        The table, with its ``period`` validated, or None when the
        value is the bare duration form.

    Raises
    ------
    NextestConfigurationError
        If the value is neither a table nor a duration, or is a table
        whose ``period`` is absent or is not a duration string.
    """
    match value:
        case str():
            return None
        case dict():
            _period_of(path, value)
            return value
        case _:
            message = f"{path}.slow-timeout is neither a table nor a duration"
            raise NextestConfigurationError(message, field="slow-timeout", value=value)


def _period_of(path: str, table: dict[str, object]) -> str:
    """Return a ``slow-timeout`` table's period, refusing an absent or malformed one.

    Absent and malformed are separated. A table with no ``period`` key
    is missing a setting; a table with ``period = 0`` has one and has
    written it as something nextest will not read. Both were reported
    as "names no period" with the whole table as the value, so a caller
    could not tell which had happened or which key to look at.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    table : dict[str, object]
        The parsed ``slow-timeout`` table.

    Returns
    -------
    str
        The period's text.

    Raises
    ------
    NextestConfigurationError
        If the key is absent, reported with the table as its value, or
        is present and not a duration string, reported by
        :func:`_duration` with ``field="period"`` and the offending
        value itself.
    """
    if "period" not in table:
        message = f"{path}.slow-timeout names no period: {table!r}"
        raise NextestConfigurationError(message, field="period", value=table)
    return _duration(f"{path}.slow-timeout", "period", table["period"])


def _table_budget(path: str, table: dict[str, object]) -> Fraction:
    """Return one inline ``slow-timeout`` table's per-test budget.

    Parameters
    ----------
    path : str
        The dotted path of the declaring table, for the message.
    table : dict[str, object]
        The parsed table.

    Returns
    -------
    Fraction
        The period multiplied by ``terminate-after``, in seconds,
        exactly.

    A table naming no ``period``, or naming one nextest will not read,
    raises :class:`NextestConfigurationError` from :func:`_period_of`,
    and a ``terminate-after`` that is not a positive integer raises the
    same from :func:`_multiplier`.

    Raises
    ------
    UnboundedTestError
        If the table names no ``terminate-after``, so nextest warns
        about a slow test forever and never stops it.
    """
    period = _period_of(path, table)
    multiplier = table.get("terminate-after")
    if multiplier is None:
        message = (
            f"{path}.slow-timeout sets no terminate-after, so nextest marks "
            f"the test slow and lets it run on; there is no per-test tier to "
            f"compare against"
        )
        raise UnboundedTestError(message, field="terminate-after", value=table)
    return exact_seconds(period) * _multiplier(path, multiplier)


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
