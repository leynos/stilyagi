"""Render diagnostics in stable text and JSON formats."""

import dataclasses as dc
import json
import logging
import typing as typ

from stilyagi import diagnostics
from stilyagi.engine.text_renderer import render_text

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.fixes import Fix
    from stilyagi.model.source import SourceSpan

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class RunSummary:
    """Counts that explain the outcome of one check command run.

    Parameters
    ----------
    checked_files:
        Registered source files that the command attempted to check.
    skipped_files:
        Source candidates without a registered extractor or declined symlinked
        directory targets.
    unreadable_files:
        Checked files whose source could not be read.
    errors:
        Error-severity diagnostics.
    warnings:
        Warning-severity diagnostics.

    Examples
    --------
    >>> RunSummary(
    ...     checked_files=2,
    ...     skipped_files=1,
    ...     unreadable_files=0,
    ...     errors=1,
    ...     warnings=2,
    ... ).skipped_files
    1
    """

    checked_files: int
    skipped_files: int
    unreadable_files: int
    errors: int
    warnings: int

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
        *,
        checked_files: int,
        skipped_files: int,
        unreadable_files: int,
    ) -> typ.Self:
        """Build summary counts from diagnostics and check-loop totals.

        Parameters
        ----------
        diagnostics_list:
            The diagnostics produced by the check loop. Their severities are
            counted; their order is not significant.
        checked_files:
            Registered source files the command attempted to check.
        skipped_files:
            Distinct source candidates without a registered extractor, plus
            declined symlinked directory targets.
        unreadable_files:
            Checked files whose source could not be read.

        Returns
        -------
        RunSummary
            The run summary with per-severity counts derived from
            ``diagnostics_list`` and the supplied check-loop totals.

        Examples
        --------
        >>> from stilyagi import diagnostics
        >>> error = diagnostics.Diagnostic(path="a.md", code="IR001", message="x")
        >>> warning = diagnostics.Diagnostic(
        ...     path="b.md",
        ...     code="IR002",
        ...     message="y",
        ...     severity=diagnostics.Severity.WARNING,
        ... )
        >>> summary = RunSummary.from_diagnostics(
        ...     [error, warning],
        ...     checked_files=2,
        ...     skipped_files=0,
        ...     unreadable_files=0,
        ... )
        >>> (summary.errors, summary.warnings)
        (1, 1)
        """
        errors = 0
        warnings = 0
        for diagnostic in diagnostics_list:
            if diagnostic.severity is diagnostics.Severity.ERROR:
                errors += 1
            else:
                warnings += 1
        return cls(
            checked_files=checked_files,
            skipped_files=skipped_files,
            unreadable_files=unreadable_files,
            errors=errors,
            warnings=warnings,
        )


@dc.dataclass(frozen=True, slots=True)
class RendererRegistry:
    r"""Render diagnostics in the supported output formats.

    Examples
    --------
    >>> registry = RendererRegistry()
    >>> registry.default_format
    'text'
    >>> registry.render([], "text")
    'checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n'
    """

    default_format: str = "text"

    def render(
        self,
        diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
        output_format: str | None = None,
        summary: RunSummary | None = None,
        *,
        fix_errors: cabc.Iterable[diagnostics.FixError] = (),
    ) -> str:
        """Render diagnostics as either text or JSON.

        Parameters
        ----------
        diagnostics_list:
            The diagnostics to render. They are sorted by path, location, and
            code before rendering, so the input order is not significant.
        output_format:
            Either ``"text"`` or ``"json"``. Falls back to
            :attr:`default_format` when omitted.
        summary:
            Check-loop totals to render. Direct renderer callers that omit it
            receive a diagnostic-derived summary with zero file counts.

        Returns
        -------
        str
            The rendered diagnostics in the requested format, terminated by a
            trailing newline.

        Raises
        ------
        ValueError
            The requested output format is not supported.
        """
        effective_format = output_format or self.default_format
        ordered_diagnostics = sorted(diagnostics_list, key=_diagnostic_sort_key)
        ordered_fix_errors = sorted(fix_errors, key=_fix_error_sort_key)
        _LOGGER.debug(
            "rendering %d diagnostic(s) as %s",
            len(ordered_diagnostics),
            effective_format,
        )
        effective_summary = summary or RunSummary.from_diagnostics(
            ordered_diagnostics,
            checked_files=0,
            skipped_files=0,
            unreadable_files=0,
        )
        if effective_format == "json":
            return _render_json(
                ordered_diagnostics, effective_summary, ordered_fix_errors
            )
        if effective_format == "text":
            return render_text(
                ordered_diagnostics, effective_summary, ordered_fix_errors
            )
        _LOGGER.error("unsupported output format %r", effective_format)
        message = (
            f"unsupported output format {effective_format!r}; "
            "choose from 'text' or 'json'"
        )
        raise ValueError(message)


def _diagnostic_sort_key(
    diagnostic: diagnostics.Diagnostic,
) -> tuple[str, int, int, str]:
    """Sort diagnostics by path, location, and code."""
    return (
        diagnostic.path,
        diagnostic.line or 1,
        diagnostic.column or 1,
        diagnostic.code,
    )


def _fix_error_sort_key(
    fix_error: diagnostics.FixError,
) -> tuple[str, str, tuple[str, ...]]:
    """Sort independent fix errors without admitting them into rule ordering."""
    return fix_error.path, fix_error.identifier, fix_error.rule_codes


def _render_json(
    diagnostics_list: list[diagnostics.Diagnostic],
    summary: RunSummary,
    fix_errors: list[diagnostics.FixError],
) -> str:
    """Render diagnostics as a stable JSON document."""
    payload = {
        "schema_version": "1.0.0",
        "diagnostics": [
            diagnostic_payload(diagnostic) for diagnostic in diagnostics_list
        ],
        "fix_errors": [_fix_error_payload(fix_error) for fix_error in fix_errors],
        "summary": dc.asdict(summary),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def diagnostic_payload(diagnostic: diagnostics.Diagnostic) -> dict[str, object]:
    """Return the JSON-shaped mapping for one diagnostic.

    Parameters
    ----------
    diagnostic:
        The diagnostic to serialize.

    Returns
    -------
    dict[str, object]
        The renderer's JSON object for this diagnostic, including the
        ``span`` key alongside the existing ``location`` key.

    Examples
    --------
    >>> from stilyagi import diagnostics
    >>> payload = diagnostic_payload(
    ...     diagnostics.Diagnostic(path="a.md", code="MD001", message="m")
    ... )
    >>> payload["span"] is None
    True
    """
    return {
        "path": diagnostic.path,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "severity": diagnostic.severity.value,
        "location": {
            "line": diagnostic.line or 1,
            "column": diagnostic.column or 1,
        },
        "span": _span_payload(diagnostic.span),
        "fix_applicable": diagnostic.fix is not None,
        "fix": _fix_payload(diagnostic.fix),
    }


def _span_payload(span: SourceSpan | None) -> dict[str, int] | None:
    """Serialize a byte span, or ``None`` when the diagnostic has no source."""
    if span is None:
        return None
    return {"byte_start": span.byte_start, "byte_end": span.byte_end}


def _fix_payload(fix: Fix | None) -> dict[str, object] | None:
    """Serialize a rule-authored fix when the diagnostic carries one."""
    if fix is None:
        return None
    return {
        "title": fix.title,
        "applicability": fix.applicability.value,
        "edits": [
            {
                "byte_start": edit.byte_start,
                "byte_end": edit.byte_end,
                "replacement": edit.replacement,
            }
            for edit in fix.edits
        ],
    }


def _fix_error_payload(fix_error: diagnostics.FixError) -> dict[str, object]:
    """Serialize one engine refusal outside the selectable rule diagnostics."""
    return {
        "identifier": fix_error.identifier,
        "path": fix_error.path,
        "rule_codes": list(fix_error.rule_codes),
        "message": fix_error.message,
    }
