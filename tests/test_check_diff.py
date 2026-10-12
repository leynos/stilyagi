"""Integration coverage for non-mutating safe-fix diff previews."""

import typing as typ

import pytest
from stilyagi import cli
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    rewrite_heading_marker,
    rewrite_paragraph,
)

if typ.TYPE_CHECKING:
    import pathlib

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
        collaborators=cli.CheckCollaborators(rule_runner=rewrite_paragraph),
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
        collaborators=cli.CheckCollaborators(rule_runner=rewrite_heading_marker),
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


@pytest.mark.parametrize(
    ("flag", "field", "codes"),
    [
        pytest.param("--select", "select", ("PUN201", "PUN202"), id="select"),
        pytest.param("--ignore", "ignore", ("PUN201",), id="ignore"),
        pytest.param(
            "--extend-select", "extend_select", ("PUN202",), id="extend-select"
        ),
    ],
)
def test_check_parser_accepts_repeatable_rule_code_arguments(
    flag: str, field: str, codes: tuple[str, ...]
) -> None:
    """Collect comma-delimited rule codes from a repeated selection flag.

    This is the regression pin for a defect the parser carried silently: the
    three selection flags declared `default=()` with `action="append"`, and
    argparse copies the default before appending to it. Copying a tuple yields
    a tuple, so every one of these flags raised `AttributeError` the first time
    it was actually passed. The existing `--diff` test could not catch it
    because `--diff` is a `store_true` flag with no default to copy, which is
    why the defect survived the flags being documented in the users' guide.

    Both halves are asserted: the flag parses at all, and the codes it selected
    reach the options object. A parser that swallowed the flag without raising
    would satisfy the first half alone.
    """
    parsed = cli.build_parser().parse_args(["check", flag, ",".join(codes), "notes.md"])

    options = cli.options_from_args(parsed)
    assert codes == getattr(options, field), (
        f"expected {flag} to populate CheckOptions.{field}"
    )


def test_check_parser_defaults_repeated_rule_code_arguments_to_empty() -> None:
    """Leave every selection field empty when no selection flag is passed."""
    options = cli.options_from_args(
        cli.build_parser().parse_args(["check", "notes.md"])
    )

    assert () == options.select == options.ignore == options.extend_select, (
        "expected the selection defaults to stay empty"
    )
