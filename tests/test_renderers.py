"""Tests for diagnostic renderers."""

from __future__ import annotations

import json
import typing as typ

from stilyagi import diagnostics, engine
from syrupy.extensions.json import JSONSnapshotExtension

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


def _build_diagnostics() -> list[diagnostics.Diagnostic]:
    """Return unsorted diagnostics for renderer order checks."""
    return [
        diagnostics.Diagnostic(
            path="docs/b.md",
            code="STY002",
            message="Second",
            severity=diagnostics.Severity.WARNING,
            line=3,
            column=4,
        ),
        diagnostics.Diagnostic(
            path="docs/a.md",
            code="STY010",
            message="Later code",
            severity=diagnostics.Severity.ERROR,
            line=1,
            column=2,
        ),
        diagnostics.Diagnostic(
            path="docs/a.md",
            code="STY001",
            message="First",
            severity=diagnostics.Severity.ERROR,
            line=1,
            column=1,
        ),
    ]


def test_renderer_registry_retains_its_default_format_and_render_surface() -> None:
    """Keep the default renderer and its entrypoint explicit."""
    registry = engine.RendererRegistry()

    assert registry.default_format == "text"
    assert registry.render([], "text") == "0 diagnostics found\n"


def test_text_renderer_orders_and_formats_diagnostics(
    snapshot: SnapshotAssertion,
) -> None:
    """Render text diagnostics in path, location, and code order."""
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "text")

    assert rendered.splitlines() == [
        "docs/a.md:1:1: error STY001 First",
        "docs/a.md:1:2: error STY010 Later code",
        "docs/b.md:3:4: warning STY002 Second",
        "3 diagnostics found",
    ]
    assert rendered.splitlines() == snapshot(extension_class=JSONSnapshotExtension)


def test_json_renderer_emits_stable_diagnostic_objects(
    snapshot: SnapshotAssertion,
) -> None:
    """Render diagnostics as stable JSON objects."""
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "json")
    payload = json.loads(rendered)

    assert payload == {
        "diagnostics": [
            {
                "path": "docs/a.md",
                "code": "STY001",
                "message": "First",
                "severity": "error",
                "location": {"line": 1, "column": 1},
                "fix_applicable": False,
            },
            {
                "path": "docs/a.md",
                "code": "STY010",
                "message": "Later code",
                "severity": "error",
                "location": {"line": 1, "column": 2},
                "fix_applicable": False,
            },
            {
                "path": "docs/b.md",
                "code": "STY002",
                "message": "Second",
                "severity": "warning",
                "location": {"line": 3, "column": 4},
                "fix_applicable": False,
            },
        ],
    }
    assert payload == snapshot(extension_class=JSONSnapshotExtension)
