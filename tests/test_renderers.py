"""Tests for diagnostic renderers."""

import json
import typing as typ

from stilyagi import diagnostics, engine
from stilyagi.fixes import Fix, TextEdit
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

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

    assert_with_context(
        registry.default_format == "text",
        "expected registry.default_format == 'text'",
    )
    assert_with_context(
        registry.render([], "text")
        == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
        "expected registry.render([], 'text') to include fix counts",
    )


def test_text_renderer_orders_and_formats_diagnostics(
    snapshot: SnapshotAssertion,
) -> None:
    """Render text diagnostics in path, location, and code order."""
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "text")

    assert_with_context(
        rendered.splitlines()
        == [
            "docs/a.md:1:1: error STY001 First",
            "docs/a.md:1:2: error STY010 Later code",
            "docs/b.md:3:4: warning STY002 Second",
            "3 diagnostics found (0 safe fixes, 0 unsafe fixes)",
        ],
        "expected rendered.splitlines() == ['docs/a.md:1:1: e...",
    )
    assert_with_context(
        rendered.splitlines() == snapshot(extension_class=JSONSnapshotExtension),
        "expected rendered.splitlines() == snapshot(extension...",
    )


def test_json_renderer_emits_stable_diagnostic_objects(
    snapshot: SnapshotAssertion,
) -> None:
    """Render diagnostics as stable JSON objects."""
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "json")
    payload = json.loads(rendered)

    assert_with_context(
        payload == snapshot(extension_class=JSONSnapshotExtension),
        "expected payload == snapshot(extension_class=JSONSna...",
    )


def test_renderers_report_fix_payloads_and_fixability_counts() -> None:
    """Expose the deterministic fix contract in both renderer formats."""
    diagnostic = diagnostics.Diagnostic(
        path="docs/notes.md",
        code="PUN201",
        message="Insert a serial comma.",
        severity=diagnostics.Severity.WARNING,
        line=12,
        column=30,
        fix=Fix(
            title="Insert serial comma",
            applicability="safe",
            edits=[TextEdit(341, 341, ",")],
        ),
    )
    registry = engine.RendererRegistry()

    assert_with_context(
        json.loads(registry.render([diagnostic], "json"))
        == {
            "schema_version": "1.0.0",
            "diagnostics": [
                {
                    "path": "docs/notes.md",
                    "code": "PUN201",
                    "message": "Insert a serial comma.",
                    "severity": "warning",
                    "location": {"line": 12, "column": 30},
                    "fix_applicable": True,
                    "fix": {
                        "title": "Insert serial comma",
                        "applicability": "safe",
                        "edits": [
                            {
                                "byte_start": 341,
                                "byte_end": 341,
                                "replacement": ",",
                            },
                        ],
                    },
                },
            ],
            "fix_errors": [],
        },
        "expected JSON output to include the versioned fix payload",
    )
    assert_with_context(
        registry.render([diagnostic], "text").splitlines()[-1]
        == "1 diagnostic found (1 safe fix, 0 unsafe fixes)",
        "expected text output to disclose safe and unsafe fix counts",
    )
