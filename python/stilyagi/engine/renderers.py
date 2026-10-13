"""Render diagnostics in stable text and JSON formats."""

import dataclasses as dc
import json
import logging
import typing as typ

from stilyagi import diagnostics

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.fixes import Fix

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
            return _render_text(
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


def _render_text(
    diagnostics_list: list[diagnostics.Diagnostic],
    summary: RunSummary,
    fix_errors: list[diagnostics.FixError],
) -> str:
    """Render diagnostics as one human-readable line per finding."""
    lines = [
        f"{diagnostic.path}:{diagnostic.line or 1}:{diagnostic.column or 1}: "
        f"{diagnostic.severity.value} {diagnostic.code} {diagnostic.message}"
        for diagnostic in diagnostics_list
    ]
    lines.extend(_render_fix_error(fix_error) for fix_error in fix_errors)
    lines.append(_summary_line(diagnostics_list, fix_errors, summary))
    return "\n".join(lines) + "\n"


def _render_fix_error(fix_error: diagnostics.FixError) -> str:
    """Render one engine-level refusal with its distinct non-rule prefix.

    The rule-code segment is omitted rather than printed empty when a refusal
    names no rule. Two of the seven identifiers -- `changed-on-disk` and
    `standard-input` -- are raised by the executor and the phase-one wrapper,
    not by a rule's proposed edit, so they carry no codes by construction.
    Joining an empty tuple yields the empty string, which rendered as a
    dangling `: ` after the path.

    Returns
    -------
    str
        One line naming the refusal's origin, path, and message.
    """
    rule_codes = ", ".join(fix_error.rule_codes)
    origin = f"{rule_codes}: " if rule_codes else ""
    return f"{fix_error.identifier}: {fix_error.path}: {origin}{fix_error.message}"


def _summary_line(
    diagnostics_list: list[diagnostics.Diagnostic],
    fix_errors: list[diagnostics.FixError],
    summary: RunSummary,
) -> str:
    """Return the run summary as one line, with fix counts when a plan exists.

    The file and severity totals are the command's own accounting and are
    always present. The fix counts are appended only when the run actually
    handled a fix -- at least one diagnostic carries a payload, or a plan was
    refused. That condition is what keeps a plain check's summary byte-stable
    against the documented shape: a run with nothing fixable has nothing to
    say about fixes, and a count of zero against every ordinary run would be
    noise the contract test would have to pin forever.

    The two nouns pluralize independently because a file can offer both: one
    safe edit applied automatically and one unsafe edit withheld.

    Returns
    -------
    str
        The summary line, with fix counts appended when the run handled one.
    """
    fix_counts = _fix_counts(diagnostics_list, fix_errors)
    line = (
        "checked "
        f"{summary.checked_files} files ({summary.skipped_files} skipped, "
        f"{summary.unreadable_files} unreadable); {summary.errors} errors, "
        f"{summary.warnings} warnings"
    )
    if fix_counts is None:
        return line
    safe_count, unsafe_count = fix_counts
    return (
        f"{line}; {_count_label(safe_count, 'safe fix')}, "
        f"{_count_label(unsafe_count, 'unsafe fix')}"
    )


def _fix_counts(
    diagnostics_list: list[diagnostics.Diagnostic],
    fix_errors: list[diagnostics.FixError],
) -> tuple[int, int] | None:
    """Count the safe and unsafe fixes on offer, or ``None`` if there are none.

    A refusal counts as evidence that a plan ran even when no diagnostic
    carries a payload -- an unsafe fix is withheld rather than attached, and
    reporting nothing about it would hide the one case the counts exist for.

    Returns
    -------
    tuple[int, int] | None
        The safe and unsafe counts, or ``None`` when the run handled no fix.
    """
    safe_count = sum(
        diagnostic.fix is not None and diagnostic.fix.applicability == "safe"
        for diagnostic in diagnostics_list
    )
    unsafe_count = sum(
        diagnostic.fix is not None and diagnostic.fix.applicability == "unsafe"
        for diagnostic in diagnostics_list
    )
    handled_a_fix = bool(safe_count or unsafe_count or fix_errors)
    if handled_a_fix:
        return safe_count, unsafe_count
    return None


def _count_label(count: int, noun: str) -> str:
    """Pluralize a counted text-renderer noun."""
    suffix = "" if count == 1 else "es"
    return f"{count} {noun}{suffix}"


def _render_json(
    diagnostics_list: list[diagnostics.Diagnostic],
    summary: RunSummary,
    fix_errors: list[diagnostics.FixError],
) -> str:
    """Render diagnostics as a stable JSON document."""
    payload = {
        "schema_version": "1.0.0",
        "diagnostics": [
            _diagnostic_payload(diagnostic) for diagnostic in diagnostics_list
        ],
        "fix_errors": [_fix_error_payload(fix_error) for fix_error in fix_errors],
        "summary": dc.asdict(summary),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _diagnostic_payload(diagnostic: diagnostics.Diagnostic) -> dict[str, object]:
    """Serialize one diagnostic without coupling rendering to execution flags."""
    return {
        "path": diagnostic.path,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "severity": diagnostic.severity.value,
        "location": {
            "line": diagnostic.line or 1,
            "column": diagnostic.column or 1,
        },
        "fix_applicable": diagnostic.fix is not None,
        "fix": _fix_payload(diagnostic.fix),
    }


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
