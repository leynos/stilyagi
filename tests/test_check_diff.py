"""Integration coverage for non-mutating safe-fix diff previews."""

import typing as typ

from stilyagi import cli, diagnostics
from stilyagi.fixes import Applicability, Fix, TextEdit
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context
from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from stilyagi import config, model
    from syrupy.assertion import SnapshotAssertion


def test_diff_prints_a_safe_preview_without_mutating_the_source(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """Reserve stdout for a safe patch and report diagnostics on stderr."""
    target = tmp_path / "notes.md"
    original = "Paragraph text.\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), diff=True),
        collaborators=cli.CheckCollaborators(rule_runner=_rewrite_paragraph),
    )
    captured = capsys.readouterr()

    assert_with_context(
        target.read_text(encoding="utf-8") == original,
        "expected the diff preview to leave the source unchanged",
    )
    assert_with_context(
        {
            "exit_code": exit_code,
            "stdout": captured.out,
            "stderr": captured.err,
        }
        == snapshot(extension_class=JSONSnapshotExtension),
        "expected the diff preview stream contract to match its snapshot",
    )


def test_diff_reports_refused_edits_on_the_diagnostic_stream(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep a planner refusal out of the patch while making it auditable."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), diff=True),
        collaborators=cli.CheckCollaborators(rule_runner=_rewrite_heading_marker),
    )
    captured = capsys.readouterr()

    assert exit_code == 1, "expected an unfixed diagnostic to exit one"
    assert not captured.out, "expected a refused edit to emit no patch"
    assert_with_context(
        "fix-error/synthetic-span: notes.md: PUN201:" in captured.err,
        "expected the refusal to use the separate fix-error channel",
    )
    assert_with_context(
        "file was not modified" in captured.err,
        "expected the refusal to state the file remained untouched",
    )


def test_check_parser_sets_the_diff_option() -> None:
    """Expose the non-mutating preview switch through the check parser."""
    parsed = cli.build_parser().parse_args(["check", "--diff", "notes.md"])

    assert cli.CheckOptions(targets=("notes.md",), diff=True) == cli.options_from_args(
        parsed
    ), "expected --diff to populate the immutable check options"


def _rewrite_paragraph(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer one safe replacement against a source-backed paragraph span."""
    span = find_source_span(document, "Paragraph")
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Use the preferred paragraph term.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Rewrite paragraph",
                Applicability.SAFE,
                (TextEdit.replace(span, "Section"),),
            ),
        )
    ]


def _rewrite_heading_marker(
    _document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer a deliberately unsafe synthetic-span edit for stream testing."""
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Do not change the heading marker automatically.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Remove heading marker",
                Applicability.SAFE,
                (TextEdit(0, 1, ""),),
            ),
        )
    ]
