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
    """Return the per-test budget one ``slow-timeout`` declares, in exact seconds."""
    # A value naming no terminate-after, in either spelling, raises
    # UnboundedTestError from the helper that reads it; one that is neither
    # a table nor a duration raises NextestConfigurationError from
    # _slow_timeout_table.
    table = _slow_timeout_table(path, value)
    if table is None:
        _bare_budget(path, typ.cast("str", value))
    return _table_budget(path, table)


def _slow_timeout_table(path: str, value: object) -> dict[str, object] | None:
    """Return a ``slow-timeout``'s validated table, or None for the bare form."""
    # The single place that decides what a well-formed slow-timeout is.
    # Two readers of this one field once disagreed: the budget derivation
    # refused `slow-timeout = 0` and a malformed period, while grace_period
    # filtered both out and returned nextest's default for a file the
    # runner will not load. The bare form is validated as a duration here
    # and answered with None; that it bounds no test is _bare_budget's
    # judgement, and it carries no grace period either way.
    match value:
        case str():
            exact_seconds(value)
            return None
        case dict():
            _period_of(path, value)
            return value
        case _:
            message = f"{path}.slow-timeout is neither a table nor a duration"
            raise NextestConfigurationError(message, field="slow-timeout", value=value)


def _period_of(path: str, table: dict[str, object]) -> str:
    """Return a ``slow-timeout`` table's period, refusing an absent or malformed one."""
    # Absent and malformed are reported apart: an absent key is reported
    # with the table as its value, and a present non-duration by _duration
    # with field="period" and the offending value itself.
    if "period" not in table:
        message = f"{path}.slow-timeout names no period: {table!r}"
        raise NextestConfigurationError(message, field="period", value=table)
    return _duration(f"{path}.slow-timeout", "period", table["period"])


def _table_budget(path: str, table: dict[str, object]) -> Fraction:
    """Return one inline ``slow-timeout`` table's per-test budget, in exact seconds."""
    # No terminate-after means nextest warns forever and never stops the
    # test, so that raises UnboundedTestError rather than returning a budget.
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
    """Refuse a ``slow-timeout`` written as a bare duration, which bounds no test."""
    message = (
        f'{path}.slow-timeout = "{period}" sets a warning period with no '
        f"terminate-after, so nextest reports the test as slow and never "
        f"stops it; there is no per-test tier to compare against"
    )
    raise UnboundedTestError(message, field="slow-timeout", value=period)
