"""Tests for diagnostic renderers."""

import json
import typing as typ

from stilyagi import diagnostics, engine
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
        == "checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected registry.render([], 'text') to render an empty summary",
    )


def test_text_renderer_orders_and_formats_diagnostics(
    snapshot: SnapshotAssertion,
) -> None:
    """Render text diagnostics in path, location, and code order."""
    summary = engine.RunSummary(
        checked_files=3,
        skipped_files=1,
        unreadable_files=0,
        errors=2,
        warnings=1,
    )
    rendered = engine.RendererRegistry().render(
        _build_diagnostics(),
        "text",
        summary,
    )

    assert_with_context(
        rendered.splitlines()
        == [
            "docs/a.md:1:1: error STY001 First",
            "docs/a.md:1:2: error STY010 Later code",
            "docs/b.md:3:4: warning STY002 Second",
            "checked 3 files (1 skipped, 0 unreadable); 2 errors, 1 warnings",
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
    summary = engine.RunSummary(
        checked_files=3,
        skipped_files=1,
        unreadable_files=0,
        errors=2,
        warnings=1,
    )
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "json", summary)
    payload = json.loads(rendered)

    assert_with_context(
        payload["summary"]
        == {
            "checked_files": 3,
            "skipped_files": 1,
            "unreadable_files": 0,
            "errors": 2,
            "warnings": 1,
        },
        "expected payload['summary'] to carry the check-run totals",
    )

    assert_with_context(
        payload == snapshot(extension_class=JSONSnapshotExtension),
        "expected payload == snapshot(extension_class=JSONSna...",
    )


def test_omitted_summary_is_derived_from_mixed_diagnostics() -> None:
    """Derive error and warning counts when a caller omits the run summary."""
    rendered = engine.RendererRegistry().render(_build_diagnostics(), "text")

    assert_with_context(
        rendered.splitlines()[-1]
        == "checked 0 files (0 skipped, 0 unreadable); 2 errors, 1 warnings",
        "expected the derived summary to count 2 errors and 1 warning",
    )


def test_omitted_summary_is_derived_in_json_output() -> None:
    """Keep JSON summary counts consistent when a caller omits the run summary."""
    payload = json.loads(
        engine.RendererRegistry().render(_build_diagnostics(), "json"),
    )

    assert_with_context(
        payload["summary"]
        == {
            "checked_files": 0,
            "skipped_files": 0,
            "unreadable_files": 0,
            "errors": 2,
            "warnings": 1,
        },
        "expected the derived JSON summary to count 2 errors and 1 warning",
    )
