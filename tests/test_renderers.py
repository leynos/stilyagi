"""Tests for diagnostic renderers."""

import json
import typing as typ

import pytest
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


def test_an_unsupported_output_format_is_refused() -> None:
    """A format the registry does not render is an error, not a fallback."""
    with pytest.raises(ValueError, match="unsupported output format 'yaml'"):
        engine.RendererRegistry().render([], "yaml")


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


def _refusal(identifier: str, rule_codes: tuple[str, ...]) -> diagnostics.FixError:
    """Return one refusal with the given identifier and contributing codes.

    Returns
    -------
    diagnostics.FixError
        A refusal naming `notes.md`. The renderer consumes `FixError` directly,
        so the test states the exact refusal a renderer will see rather than
        routing it through a `PlannedFile` that exists for other reasons.
    """
    return diagnostics.FixError(
        path="notes.md",
        identifier=identifier,
        rule_codes=rule_codes,
        message="the file was left alone",
    )


def _render_refusals(*refusals: diagnostics.FixError) -> str:
    """Render those refusals through the text renderer."""
    return engine.RendererRegistry().render([], "text", fix_errors=list(refusals))


class TestRefusalRendering:
    """A refusal names its origin, and omits what it does not have."""

    def test_a_refusal_with_no_rule_codes_omits_the_empty_segment(self) -> None:
        """No code is rendered as nothing, not as a dangling separator.

        `changed-on-disk` and `standard-input` are raised by the executor and
        the phase-one wrapper rather than by a rule's proposed edit, so they
        carry no rule codes by construction. Joining an empty tuple yields the
        empty string, which used to render as `path: : message`.
        """
        rendered = _render_refusals(_refusal("fix-error/changed-on-disk", ()))

        assert_with_context(
            "fix-error/changed-on-disk: notes.md: the file was left alone" in rendered,
            "expected the refusal line to name the path then the message",
        )
        assert_with_context(
            ": :" not in rendered,
            "expected no empty rule-code segment in the rendered refusal",
        )

    def test_a_refusal_with_rule_codes_still_names_them(self) -> None:
        """The codes are what tells a user which rule could not be applied.

        Paired with the case above, this pins that the fix narrowed one
        rendering rather than removing the segment outright: a conflict still
        has to name every rule that contributed to it.
        """
        rendered = _render_refusals(
            _refusal("fix-error/overlapping-edits", ("PUN201", "PUN202"))
        )

        assert_with_context(
            "fix-error/overlapping-edits: notes.md: PUN201, PUN202: "
            "the file was left alone" in rendered,
            "expected the refusal to name both contributing rules",
        )
