"""Diagnostic adapters for the check command."""

from __future__ import annotations

import collections.abc as cabc

from stilyagi import diagnostics, model
from stilyagi.diagnostics_location import line_column_from_offset


def map_ir_errors(
    document: model.Document,
    reported_path: str,
) -> list[diagnostics.Diagnostic]:
    """Map canonical IR errors into public diagnostics.

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
        return []

    raw_errors = ir.get("errors")
    if not isinstance(raw_errors, cabc.Sequence) or isinstance(
        raw_errors,
        (str, bytes),
    ):
        return []

    line_index = _coerce_line_index(ir.get("line_index"))

    mapped_errors = (
        _map_one_error(error, line_index, reported_path) for error in raw_errors
    )
    return [error for error in mapped_errors if error is not None]


def _map_one_error(
    error: object,
    line_index: tuple[int, ...] | None,
    reported_path: str,
) -> diagnostics.Diagnostic | None:
    """Map one raw IR error entry into a diagnostic, if well formed."""
    if not isinstance(error, cabc.Mapping):
        return None

    line, column = line_column_from_offset(
        line_index,
        _byte_start_from_span(error.get("span")),
    )
    return diagnostics.Diagnostic(
        path=reported_path,
        code="IR000",
        message=str(error.get("message", "")),
        severity=diagnostics.Severity.ERROR,
        line=line,
        column=column,
    )


def _byte_start_from_span(span: object) -> int | None:
    """Return the span's byte start when the IR provides one."""
    if not isinstance(span, cabc.Mapping):
        return None
    byte_start = span.get("byte_start")
    return byte_start if isinstance(byte_start, int) else None


def _coerce_line_index(raw_line_index: object) -> tuple[int, ...] | None:
    """Return a typed tuple of byte offsets when the IR provides one."""
    if not isinstance(raw_line_index, cabc.Sequence) or isinstance(
        raw_line_index,
        (str, bytes),
    ):
        return None

    line_starts: list[int] = []
    for start in raw_line_index:
        if not isinstance(start, int):
            return None
        line_starts.append(start)
    return tuple(line_starts)
