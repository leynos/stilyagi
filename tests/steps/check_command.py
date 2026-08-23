"""Shared BDD steps for the `stilyagi check` command."""

import io
import json
import logging
import pathlib
import sys
import typing as typ

import pytest
from pytest_bdd import given, parsers, then, when
from stilyagi import cli, engine, model

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus


class CheckCommandState(typ.TypedDict, total=False):
    """State shared across the `stilyagi check` scenarios."""

    root: pathlib.Path
    exit_code: int
    stdout: str
    stderr: str
    extracted_syntaxes: list[model.Syntax]


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
    "a temporary tree with Markdown, Python, and Rust source files",
    target_fixture="check_command_state",
)
def temporary_tree_with_mixed_source_files(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create one valid input for each registered source syntax."""
    _write_markdown(tmp_path / "docs" / "guide.md", "Guide")
    _write_source(tmp_path / "src" / "app.py", '"""Module docs."""\n')
    _write_source(tmp_path / "src" / "lib.rs", "//! Crate docs.\n")
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
    "a temporary tree containing malformed Rust",
    target_fixture="check_command_state",
)
def temporary_tree_containing_malformed_rust(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create Rust source whose parser recovery yields an anomaly diagnostic."""
    _write_source(
        tmp_path / "src" / "broken.rs",
        "//! Documentation before malformed Rust source.\nfn broken( {\n",
    )
    return {"root": tmp_path}


@given(
    "a temporary tree containing a Python file with a blanket suppression",
    target_fixture="check_command_state",
)
def temporary_tree_containing_blanket_python_suppression(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create an authored Python directive violation that must gate the run."""
    _write_source(tmp_path / "src" / "app.py", "# stilyagi: disable\n")
    return {"root": tmp_path}


@given(
    'a temporary tree with files "docs/guide.md", "src/app.py", and "notes.txt"',
    target_fixture="check_command_state",
)
def temporary_tree_with_registered_and_unregistered_files(
    tmp_path: pathlib.Path,
) -> CheckCommandState:
    """Create two registered files and one source candidate to skip."""
    _write_markdown(tmp_path / "docs" / "guide.md", "Guide")
    _write_source(tmp_path / "src" / "app.py", '"""Module docs."""\n')
    _write_source(tmp_path / "notes.txt", "Not a registered source.\n")
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
                    "code": "suppression-blanket-forbidden",
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


@given("the extractor records selected syntaxes")
def extractor_records_selected_syntaxes(
    check_command_state: CheckCommandState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace extraction with a recorder that preserves the chosen syntax."""
    extracted_syntaxes: list[model.Syntax] = []

    def record_syntax(_source: str, syntax: model.Syntax) -> model.Document:
        """Record one selected syntax and return an empty document."""
        extracted_syntaxes.append(syntax)
        return model.Document(syntax=syntax)

    check_command_state["extracted_syntaxes"] = extracted_syntaxes
    monkeypatch.setattr(engine, "extract_document", record_syntax)


@when(parsers.parse('I run "{command}" in that tree'))
def run_stilyagi_command_in_that_tree(
    check_command_state: CheckCommandState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    command: str,
) -> None:
    """Run one quoted `stilyagi` invocation in-process and capture it."""
    program, *argv = command.split()
    assert program == "stilyagi", f"unsupported command: {command}"
    if "-" in argv:
        monkeypatch.setattr(sys, "stdin", io.StringIO("# Notes\n"))
    monkeypatch.chdir(check_command_state["root"])
    with caplog.at_level(logging.WARNING):
        check_command_state["exit_code"] = cli.main(argv)
    captured = capsys.readouterr()
    check_command_state["stdout"] = captured.out
    check_command_state["stderr"] = "\n".join(
        record.getMessage() for record in caplog.records
    )


@then("the exit code is 0")
def the_exit_code_is_zero(check_command_state: CheckCommandState) -> None:
    """Assert that the clean-tree command path succeeded."""
    assert_with_context(
        check_command_state["exit_code"] == 0,
        "expected check_command_state['exit_code'] == 0",
    )


@then("the exit code is 1")
def the_exit_code_is_one(check_command_state: CheckCommandState) -> None:
    """Assert that the synthetic-diagnostic path reports findings."""
    assert_with_context(
        check_command_state["exit_code"] == 1,
        "expected check_command_state['exit_code'] == 1",
    )


@then("the exit code is 2")
def the_exit_code_is_two(check_command_state: CheckCommandState) -> None:
    """Assert that invalid config and usage failures fail fast."""
    assert_with_context(
        check_command_state["exit_code"] == 2,
        "expected check_command_state['exit_code'] == 2",
    )


@then("the text output lists no diagnostics")
def the_text_output_lists_no_diagnostics(
    check_command_state: CheckCommandState,
) -> None:
    """Assert the rendered text contract for an empty run."""
    assert_with_context(
        check_command_state["stdout"].endswith("0 errors, 0 warnings\n"),
        "expected check_command_state['stdout'] to end with a clean summary",
    )


@then("the selected syntaxes are Markdown, Python docstrings, and Rust doc comments")
def selected_syntaxes_cover_the_mixed_tree(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that every registered suffix selected its matching extractor."""
    assert check_command_state["extracted_syntaxes"] == [
        model.Syntax.MARKDOWN,
        model.Syntax.PYTHON_DOCSTRING,
        model.Syntax.RUST_DOC_COMMENT,
    ]


@then("the selected syntax is Rust documentation comments")
def selected_syntax_is_rust_documentation_comments(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that the stdin filename selects the Rust extractor."""
    assert check_command_state["extracted_syntaxes"] == [
        model.Syntax.RUST_DOC_COMMENT,
    ]


@then("no input was extracted")
def no_input_was_extracted(check_command_state: CheckCommandState) -> None:
    """Assert that an unregistered stdin filename is skipped."""
    assert check_command_state["extracted_syntaxes"] == []
    assert_with_context(
        "skipping stdin without a registered extractor"
        in check_command_state["stderr"],
        "expected an unregistered-stdin warning message",
    )
    assert_with_context(
        check_command_state["stdout"]
        == "checked 0 files (1 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected the skipped-stdin summary",
    )


@then("the diagnostics and processed paths follow sorted normalized order")
def the_diagnostics_and_processed_paths_follow_sorted_normalized_order(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that JSON output preserves the renderer's sorted path order."""
    payload = json.loads(check_command_state["stdout"])
    paths = [item["path"] for item in payload["diagnostics"]]
    assert_with_context(
        paths == ["a.md", "b.md", "sub/c.md"],
        "expected paths == ['a.md', 'b.md', 'sub/c.md']",
    )
    assert_with_context(
        check_command_state["stderr"] == "",
        "expected check_command_state['stderr'] == ''",
    )


@then('the text output attributes the synthetic diagnostic to "README.md"')
def the_text_output_attributes_the_synthetic_diagnostic_to_readme(
    check_command_state: CheckCommandState,
) -> None:
    """Assert the stdin path is reflected in the rendered text output."""
    assert_with_context(
        (
            check_command_state["stdout"]
            == (
                "README.md:1:1: error suppression-blanket-forbidden "
                "Synthetic IR error\n"
                "checked 1 files (0 skipped, 0 unreadable); 1 errors, 0 warnings\n"
            )
        ),
        "expected check_command_state['stdout'] == 'README.md...",
    )
    assert_with_context(
        check_command_state["stderr"] == "",
        "expected check_command_state['stderr'] == ''",
    )


@then("the text output reports a warning-severity diagnostic")
def text_output_reports_a_warning(check_command_state: CheckCommandState) -> None:
    """Assert that a recoverable extraction anomaly is non-gating output."""
    assert "warning " in check_command_state["stdout"], (
        "expected a warning-severity diagnostic"
    )


@then("the text output reports an error-severity diagnostic")
def text_output_reports_an_error(check_command_state: CheckCommandState) -> None:
    """Assert that an authored directive violation remains gating output."""
    assert "error suppression-blanket-forbidden" in check_command_state["stdout"], (
        "expected the authored-directive error diagnostic"
    )


@then("the summary reports 1 file checked and 0 errors")
def summary_reports_one_checked_file_and_no_errors(
    check_command_state: CheckCommandState,
) -> None:
    """Assert the warning-only run keeps its coverage denominator visible."""
    assert (
        "checked 1 files (0 skipped, 0 unreadable); 0 errors, 1 warnings"
        in check_command_state["stdout"]
    ), "expected the warning-only run summary"


@then("the summary reports 2 files checked")
def summary_reports_two_checked_files(check_command_state: CheckCommandState) -> None:
    """Assert that unregistered candidates are counted as skipped."""
    assert (
        "checked 2 files (1 skipped, 0 unreadable); 0 errors, 0 warnings"
        in check_command_state["stdout"]
    ), "expected the registered and skipped file totals"


@then("the standard error reports an actionable configuration error")
def the_standard_error_reports_an_actionable_configuration_error(
    check_command_state: CheckCommandState,
) -> None:
    """Assert that invalid discovery errors are routed to stderr."""
    assert_with_context(
        "stilyagi check:" in check_command_state["stderr"],
        "expected 'stilyagi check:' in check_command_state['s...",
    )
    assert_with_context(
        "toml" in check_command_state["stderr"].lower(),
        "expected 'toml' in check_command_state['stderr'].low...",
    )
    assert_with_context(
        check_command_state["stdout"] == "",
        "expected check_command_state['stdout'] == ''",
    )


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for a BDD scenario."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")


def _write_source(path: pathlib.Path, source: str) -> None:
    """Write source text for a mixed-source BDD scenario."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
