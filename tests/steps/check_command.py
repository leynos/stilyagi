"""Shared BDD steps for the `stilyagi check` command."""

from __future__ import annotations

import io
import json
import sys
import typing as typ

from pytest_bdd import given, parsers, then, when
from stilyagi import cli, engine, model

from tests.support.malformed_corpus import materialize_malformed_corpus

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


class CheckCommandState(typ.TypedDict, total=False):
    """State shared across the `stilyagi check` scenarios."""

    root: pathlib.Path
    exit_code: int
    stdout: str
    stderr: str


@given(
    "a temporary tree with two well-formed Markdown files",
    target_fixture="check_command_state",
)
def temporary_tree_with_two_well_formed_markdown_files(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create a Markdown tree that should produce no diagnostics."""
    _write_markdown(tmp_path / "docs" / "alpha.md", "Alpha")
    _write_markdown(tmp_path / "docs" / "beta.md", "Beta")
    return {"root": tmp_path}


@given(
    'a temporary tree with Markdown files "b.md", "a.md", and "sub/c.md"',
    target_fixture="check_command_state",
)
def temporary_tree_with_markdown_files_in_unsorted_order(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create a Markdown tree with intentionally unsorted file names."""
    _write_markdown(tmp_path / "b.md", "Bravo")
    _write_markdown(tmp_path / "a.md", "Alpha")
    _write_markdown(tmp_path / "sub" / "c.md", "Charlie")
    return {"root": tmp_path}


@given(
    "a temporary tree containing malformed Markdown",
    target_fixture="check_command_state",
)
def temporary_tree_containing_malformed_markdown(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Materialise the real malformed Markdown corpus as discoverable files."""
    materialize_malformed_corpus(tmp_path / "docs")
    return {"root": tmp_path}


@given(
    "a temporary tree with an invalid stilyagi.toml",
    target_fixture="check_command_state",
)
def temporary_tree_with_an_invalid_stilyagi_toml(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create a tree whose discovered config should fail fast."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    return {"root": tmp_path}


@given(
    "a temporary tree with a stilyagi.toml and a Markdown file",
    target_fixture="check_command_state",
)
def temporary_tree_with_a_stilyagi_toml_and_a_markdown_file(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create a tree where isolated mode must ignore the discovered config."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    return {"root": tmp_path}


@given("the extractor emits one synthetic IR error per file")
def extractor_emits_one_synthetic_ir_error_per_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace the Rust-backed extractor with a deterministic IR error stub."""
    synthetic_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "line_index": [0, 8],
            "errors": [
                {
                    "message": "Synthetic IR error",
                    "span": {"byte_start": 0},
                },
            ],
        },
    )
    monkeypatch.setattr(
        engine,
        "extract_document",
        lambda _source, _syntax: synthetic_document,
    )


@when(parsers.parse('I run "{command}" in that tree'))
def run_stilyagi_command_in_that_tree(
    check_command_state: CheckCommandState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Run one quoted `stilyagi` invocation in-process and capture it."""
    program, *argv = command.split()
    assert program == "stilyagi", f"unsupported command: {command}"
    if "-" in argv:
        monkeypatch.setattr(sys, "stdin", io.StringIO("# Notes\n"))
    monkeypatch.chdir(check_command_state["root"])
    check_command_state["exit_code"] = cli.main(argv)
    captured = capsys.readouterr()
    check_command_state["stdout"] = captured.out
    check_command_state["stderr"] = captured.err


@then("the exit code is 0")
def the_exit_code_is_zero(check_command_state: CheckCommandState) -> None:
    """Assert that the clean-tree command path succeeded."""
    assert check_command_state["exit_code"] == 0


@then("the exit code is 1")
def the_exit_code_is_one(check_command_state: CheckCommandState) -> None:
    """Assert that the synthetic-diagnostic path reports findings."""
    assert check_command_state["exit_code"] == 1


@then("the exit code is 2")
def the_exit_code_is_two(check_command_state: CheckCommandState) -> None:
    """Assert that invalid config and usage failures fail fast."""
    assert check_command_state["exit_code"] == 2


@then("the text output lists no diagnostics")
def the_text_output_lists_no_diagnostics(
    check_command_state: CheckCommandState,
) -> None:
    """Assert the rendered text contract for an empty run."""
    assert check_command_state["stdout"] == "0 diagnostics found\n"
    assert check_command_state["stderr"] == ""


@then("the diagnostics and processed paths follow sorted normalized order")
def the_diagnostics_and_processed_paths_follow_sorted_normalized_order(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that JSON output preserves the renderer's sorted path order."""
    payload = json.loads(check_command_state["stdout"])
    paths = [item["path"] for item in payload["diagnostics"]]
    assert paths == ["a.md", "b.md", "sub/c.md"]
    assert check_command_state["stderr"] == ""


@then('the text output attributes the synthetic diagnostic to "README.md"')
def the_text_output_attributes_the_synthetic_diagnostic_to_readme(
    check_command_state: CheckCommandState,
) -> None:
    """Assert the stdin path is reflected in the rendered text output."""
    assert (
        check_command_state["stdout"]
        == "README.md:1:1: error IR000 Synthetic IR error\n1 diagnostic found\n"
    )
    assert check_command_state["stderr"] == ""


@then("the standard error reports an actionable configuration error")
def the_standard_error_reports_an_actionable_configuration_error(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that invalid discovery errors are routed to stderr."""
    assert "stilyagi check:" in check_command_state["stderr"]
    assert "toml" in check_command_state["stderr"].lower()
    assert check_command_state["stdout"] == ""


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for a BDD scenario."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
