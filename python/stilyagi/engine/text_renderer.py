"""Render diagnostics and the run summary as human-readable text.

The JSON backend lives with :class:`stilyagi.engine.renderers.RendererRegistry`
because its document shape is part of the command's contract. This module holds
the other half: one line per finding, then the summary sentence, so the text
format can be read and changed without reading past the JSON payloads.
"""

import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi import diagnostics
    from stilyagi.engine.renderers import RunSummary


def render_text(
    diagnostics_list: list[diagnostics.Diagnostic],
    summary: RunSummary,
    fix_errors: list[diagnostics.FixError],
) -> str:
    """Render diagnostics as one human-readable line per finding.

    Parameters
    ----------
    diagnostics_list:
        The diagnostics to render, already ordered by the caller.
    summary:
        Check-loop totals to render as the closing summary line.
    fix_errors:
        Engine refusals to render after the findings, already ordered.

    Returns
    -------
    str
        The findings, any refusals, and the summary line, newline-terminated.

    Examples
    --------
    >>> from stilyagi import diagnostics
    >>> from stilyagi.engine.renderers import RunSummary
    >>> finding = diagnostics.Diagnostic(path="a.md", code="MD001", message="Jump.")
    >>> output = render_text(
    ...     [finding], RunSummary(1, 0, 0, 1, 0), []
    ... ).splitlines()
    >>> output[0]
    'a.md:1:1: error MD001 Jump.'
    """
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
