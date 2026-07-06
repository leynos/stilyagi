"""Render diagnostics in stable text and JSON formats."""

from __future__ import annotations

import dataclasses as dc
import json
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics


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
        """Render diagnostics as either text or JSON."""
        effective_format = output_format or self.default_format
        ordered_diagnostics = sorted(
            diagnostics_list,
            key=_diagnostic_sort_key,
        )
        if effective_format == "json":
            return _render_json(ordered_diagnostics)
        if effective_format == "text":
            return _render_text(ordered_diagnostics)
        raise ValueError(effective_format)


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
        f"{diagnostic.code} {diagnostic.message}"
        for diagnostic in diagnostics_list
    ]
    count = len(diagnostics_list)
    summary = "1 diagnostic found" if count == 1 else f"{count} diagnostics found"
    lines.append(summary)
    return "\n".join(lines) + "\n"


def _render_json(
    diagnostics_list: list[diagnostics.Diagnostic],
) -> str:
    """Render diagnostics as a stable JSON document."""
    payload = {
        "diagnostics": [
            {
                "path": diagnostic.path,
                "code": diagnostic.code,
                "message": diagnostic.message,
                "severity": diagnostic.severity.value,
                "location": {
                    "line": diagnostic.line or 1,
                    "column": diagnostic.column or 1,
                },
                "fix_applicable": diagnostic.fix is not None,
            }
            for diagnostic in diagnostics_list
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
