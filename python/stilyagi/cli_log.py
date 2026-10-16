"""Configure the console log handler that makes structured fields visible.

The command logs under `--verbose`, and every record it emits carries its
decision in the ``extra`` mapping rather than in its message. The stdlib's
default formatter renders the message alone and drops ``extra`` entirely, so a
per-file decision reached the user as the bare sentence `fix plan decided` --
no file identity, none of the counters that are the reason the record exists.
A structured field that never reaches a human is not observability; it is a
value the process computed and threw away.

This module owns the one handler that fixes that, and the fixed field list it
renders. It exists apart from `cli_fix` because it serves the whole command
rather than the fix reporter: `cli` installs the handler, `plan` emits records
the handler formats, and neither should have to import the other's reporting
half to get them displayed.

It owns a second, narrower handler as well. Expected operational failures are
user-facing *output*, not diagnostics: they have to reach a terminal whatever
the ambient logging configuration is, including one whose root handler is
installed by an embedding application. The command logger therefore carries its
own non-propagating handler, so one emission is enough and a root handler
cannot double it.

Dependency direction runs inward: this module imports nothing from `stilyagi`.
"""

import logging
import sys

__all__ = [
    "LOG_FORMAT",
    "STRUCTURED_FIELDS",
    "append_structured_fields",
    "command_warning_handler",
    "log_handler",
]

#: The console layout for one record: level, emitting logger, then the message.
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

#: Every ``extra`` key any log record in this command sets, sorted. Rendering a
#: fixed set keeps the fields visible while leaving the record itself untouched,
#: so a `caplog` consumer still reads the attributes as attributes. A record
#: carrying none of them gains no empty key/value noise.
#:
#: A new ``extra`` key has to be added here or it is written and never shown,
#: which is the defect this list exists to prevent. The cost of the list being
#: explicit is that it is one more place to keep in step; the benefit is that
#: "which fields does the log actually carry" has a single answer.
STRUCTURED_FIELDS = (
    "accepted_count",
    "bytes_delta",
    "candidate_count",
    "checked_files",
    "coalesced_count",
    "conflict_state",
    "detail",
    "elapsed_ms",
    "files_aborted",
    "files_written",
    "manual_count",
    "operation",
    "outcome",
    "patch_byte_count",
    "patched_files",
    "path",
    "planned_edits",
    "planned_files",
    "refused_edits",
    "rejected_count",
    "rejection_category",
    "rejection_count",
    "replacement_byte_count",
    "rule_codes",
    "source_backed_spans",
    "unfixable_count",
    "withheld_unsafe_count",
)


def log_handler() -> logging.StreamHandler:
    """Build the console handler that makes this command's fields visible.

    Returns
    -------
    logging.StreamHandler
        A stream handler on standard error with a formatter that appends every
        structured field a record carries, in a fixed order. The narrower type
        states what this builds; it is still a `logging.Handler` to every
        caller that installs it, and `logging.basicConfig` accepts it there.

    Examples
    --------
    >>> handler = log_handler()
    >>> handler.formatter is not None
    True
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(append_structured_fields)
    return handler


def append_structured_fields(record: logging.LogRecord) -> bool:
    """Move a record's structured fields from ``extra`` into its message.

    Returns
    -------
    bool
        Always true: the filter adds presentation and never drops a record.
    """
    fields = [
        f"{name}={getattr(record, name)!r}"
        for name in STRUCTURED_FIELDS
        if hasattr(record, name)
    ]
    if fields:
        record.msg = f"{record.getMessage()} ({', '.join(fields)})"
        record.args = ()
    return True


class _CommandWarningHandler(logging.StreamHandler):
    """Identify, by type, the handler :func:`configure_command_warning_handler` owns."""


def command_warning_handler() -> logging.Handler:
    """Build the handler that carries expected failures to standard error.

    It renders the message alone: an expected failure is a sentence for a
    human, not a structured record, so the field-rendering filter would add
    nothing and could only obscure it.

    Returns
    -------
    logging.Handler
        A stream handler on standard error, warning level and above.

    Examples
    --------
    >>> handler = command_warning_handler()
    >>> handler.level == logging.WARNING
    True
    """
    handler = _CommandWarningHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


#: The logger expected operational failures are reported through. It is named
#: rather than module-scoped so that one handler serves every reporter, and so
#: that a test can assert which logger a failure reached.
_COMMAND_LOGGER_NAME = "stilyagi.command"


def command_logger() -> logging.Logger:
    """Return the logger expected failures are reported through.

    A reporter calls this rather than holding a module logger because the
    handler is installed on the command logger *by name*: a caller that bound
    the object at import time would still see the right logger, but a reader
    cannot tell from the call site that the propagation contract is what makes
    one emission sufficient. Going through the name makes that explicit.

    Returns
    -------
    logging.Logger
        The command logger, without installing a handler on it.

    Examples
    --------
    >>> command_logger() is logging.getLogger("stilyagi.command")
    True
    """
    return logging.getLogger(_COMMAND_LOGGER_NAME)


def configure_command_warning_handler() -> None:
    """Install the command logger's own non-propagating warning handler.

    Repeated setup replaces only the handler this function owns, so repeated
    in-process CLI calls do not accumulate duplicates. Suppressing propagation
    is what keeps the message from also reaching a root handler an embedding
    application installed, which would show the user the same failure twice.

    Examples
    --------
    >>> configure_command_warning_handler()  # doctest: +SKIP
    """
    logger = command_logger()
    for handler in tuple(logger.handlers):
        if isinstance(handler, _CommandWarningHandler):
            logger.removeHandler(handler)
            handler.close()
    logger.addHandler(_CommandWarningHandler(sys.stderr))
    logger.setLevel(logging.WARNING)
    logger.propagate = False
