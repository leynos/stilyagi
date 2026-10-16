"""Reads for the dynamic fields a log record carries in ``extra``.

``logging`` stamps the values passed via ``extra`` onto the record at
runtime, so a statically typed reader sees only the base `LogRecord`
attributes. Production keeps the full list of names it stamps in
`stilyagi.cli_log.STRUCTURED_FIELDS`; tests that assert on those same values
need a read the type checker accepts, and one place to record why the read is
dynamic rather than an attribute access.
"""

import typing as typ

if typ.TYPE_CHECKING:
    import logging

__all__ = ["record_field"]


def record_field(record: logging.LogRecord, name: str) -> object:
    """Return one dynamically stamped field from a log record.

    Parameters
    ----------
    record : logging.LogRecord
        The record to read.
    name : str
        The field name, as it appears in `stilyagi.cli_log.STRUCTURED_FIELDS`.

    Returns
    -------
    object
        The stamped value, or ``None`` when the record does not carry it.
        Callers narrow it with `isinstance` before using it as anything but a
        value to compare.

    Notes
    -----
    The three-argument `getattr` is deliberate on both counts. The value is
    genuinely untyped, so a static attribute read cannot be made to
    type-check. Ruff's ``B009`` flags the constant-name form, and the default
    argument is what keeps this a dynamic read of a name that may be absent
    rather than an attribute access that always exists.

    Examples
    --------
    >>> import logging
    >>> record = logging.LogRecord("n", logging.INFO, "p", 1, "m", (), None)
    >>> record.operation = "plan_fixes"
    >>> record_field(record, "operation")
    'plan_fixes'
    >>> record_field(record, "absent") is None
    True
    """
    return getattr(record, name, None)
