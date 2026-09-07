"""Render diagnostics in stable text and JSON formats."""

import dataclasses as dc
import json
import logging
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics
    from stilyagi.fixes import Fix

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class RendererRegistry:
    r"""Render diagnostics in the supported output formats.

    Examples
    --------
    >>> registry = RendererRegistry()
    >>> registry.default_format
    'text'
    >>> registry.render([], "text")
    '0 diagnostics found\\n'
    """

    default_format: str = "text"

    def render(
        self,
        diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
        output_format: str | None = None,
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
        ordered_diagnostics = sorted(
            diagnostics_list,
            key=_diagnostic_sort_key,
        )
        _LOGGER.debug(
            "rendering %d diagnostic(s) as %s",
            len(ordered_diagnostics),
            effective_format,
        )
        if effective_format == "json":
            return _render_json(ordered_diagnostics)
        if effective_format == "text":
            return _render_text(ordered_diagnostics)
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


def _render_text(
    diagnostics_list: list[diagnostics.Diagnostic],
) -> str:
    """Render diagnostics as one human-readable line per finding."""
    lines = [
        f"{diagnostic.path}:{diagnostic.line or 1}:{diagnostic.column or 1}: "
        f"{diagnostic.severity.value} {diagnostic.code} {diagnostic.message}"
        for diagnostic in diagnostics_list
    ]
    summary = _text_summary(diagnostics_list)
    lines.append(summary)
    return "\n".join(lines) + "\n"


def _text_summary(diagnostics_list: list[diagnostics.Diagnostic]) -> str:
    """Return the diagnostic summary with visible automatic-fix counts."""
    diagnostic_count = len(diagnostics_list)
    diagnostic_label = "diagnostic" if diagnostic_count == 1 else "diagnostics"
    safe_count = sum(
        diagnostic.fix is not None and diagnostic.fix.applicability == "safe"
        for diagnostic in diagnostics_list
    )
    unsafe_count = sum(
        diagnostic.fix is not None and diagnostic.fix.applicability == "unsafe"
        for diagnostic in diagnostics_list
    )
    return (
        f"{diagnostic_count} {diagnostic_label} found "
        f"({_count_label(safe_count, 'safe fix')}, "
        f"{_count_label(unsafe_count, 'unsafe fix')})"
    )


def _count_label(count: int, noun: str) -> str:
    """Pluralize a counted text-renderer noun."""
    suffix = "" if count == 1 else "es"
    return f"{count} {noun}{suffix}"


def _render_json(
    diagnostics_list: list[diagnostics.Diagnostic],
) -> str:
    """Render diagnostics as a stable JSON document."""
    payload = {
        "schema_version": "1.0.0",
        "diagnostics": [
            _diagnostic_payload(diagnostic) for diagnostic in diagnostics_list
        ],
        "fix_errors": [],
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
