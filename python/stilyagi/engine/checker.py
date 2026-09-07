"""Diagnostic adapters for the check command."""

import collections.abc as cabc
import logging
import typing as typ

from stilyagi import diagnostics, model
from stilyagi.diagnostics_location import line_column_from_offset
from stilyagi.engine.ir_view import byte_start_from_span, line_index

_DEFAULT_IR_CODE = "IR000"

_LOGGER = logging.getLogger(__name__)


def map_ir_errors(
    document: model.Document,
    reported_path: str,
) -> list[diagnostics.Diagnostic]:
    """Map canonical IR errors into public diagnostics.

    Parameters
    ----------
    document:
        The extracted document whose ``ir`` envelope may carry recoverable
        error entries.
    reported_path:
        Command-line-relative POSIX path attributed to each diagnostic.

    Returns
    -------
    list[diagnostics.Diagnostic]
        One diagnostic per well-formed IR error entry, in source order. Returns
        an empty list when the IR is absent or carries no error sequence.

    Examples
    --------
    >>> from stilyagi import model
    >>> document = model.Document(
    ...     syntax=model.Syntax.MARKDOWN,
    ...     ir={"line_index": [0, 6, 12], "errors": []},
    ... )
    >>> map_ir_errors(document, "docs/example.md")
    []
    """
    ir = document.ir
    if ir is None:
        _LOGGER.debug("no IR envelope to map for %s", reported_path)
        return []

    raw_errors: object = ir.get("errors")
    if not isinstance(raw_errors, cabc.Sequence) or isinstance(
        raw_errors,
        (str, bytes),
    ):
        _LOGGER.debug("IR for %s carries no error sequence", reported_path)
        return []

    line_starts = line_index(document)

    errors = typ.cast("cabc.Sequence[object]", raw_errors)
    mapped_errors = (
        _map_one_error(error, line_starts, reported_path) for error in errors
    )
    diagnostics_list = [error for error in mapped_errors if error is not None]
    _LOGGER.debug("mapped %d IR error(s) for %s", len(diagnostics_list), reported_path)
    return diagnostics_list


def _map_one_error(
    error: object,
    line_index: tuple[int, ...] | None,
    reported_path: str,
) -> diagnostics.Diagnostic | None:
    """Map one raw IR error entry into a diagnostic, if well formed."""
    if not isinstance(error, cabc.Mapping):
        _LOGGER.warning(
            "skipping malformed IR error entry for %s: %r", reported_path, error
        )
        return None

    typed_error = typ.cast("cabc.Mapping[str, object]", error)
    line, column = line_column_from_offset(
        line_index,
        byte_start_from_span(typed_error.get("span")),
    )
    return diagnostics.Diagnostic(
        path=reported_path,
        code=_ir_code(typed_error.get("code")),
        message=str(typed_error.get("message", "")),
        severity=diagnostics.Severity.ERROR,
        line=line,
        column=column,
    )


def _ir_code(raw_code: object) -> str:
    """Return the IR-provided error code, or a generic placeholder."""
    if isinstance(raw_code, str) and raw_code:
        return raw_code
    return _DEFAULT_IR_CODE
