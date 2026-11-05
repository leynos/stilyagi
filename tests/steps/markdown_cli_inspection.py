"""Pytest-BDD steps for real Markdown inspection CLI processes."""

import hashlib
import json
import pathlib  # ruff: ignore[typing-only-standard-library-import] - pytest-bdd resolves step annotations at runtime.
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local argv, no shell.
import sys
import typing as typ

import pytest
from pytest_bdd import given, then, when

from tests.support.subprocess_env import python_module_environment


class MarkdownInspectionState(typ.TypedDict, total=False):
    """Mutable state shared by one Markdown inspection scenario."""

    root: pathlib.Path
    sources: dict[str, bytes]
    runs: list[subprocess.CompletedProcess[bytes]]
    last_run: subprocess.CompletedProcess[bytes]
    outside_target: pathlib.Path


@pytest.fixture
def markdown_inspection_state(tmp_path: pathlib.Path) -> MarkdownInspectionState:
    """Create a disposable process working directory for one scenario."""
    return {"root": tmp_path, "sources": {}, "runs": []}


def _root(state: MarkdownInspectionState) -> pathlib.Path:
    """Return the scenario's disposable project root."""
    return state["root"]


def _write_source(
    state: MarkdownInspectionState,
    relative_path: str,
    content: bytes,
) -> pathlib.Path:
    """Write and remember one source file for later byte comparison."""
    path = _root(state) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    state["sources"][relative_path] = content
    return path


def _run_cli(
    state: MarkdownInspectionState,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    """Invoke the built package through its Python module command boundary."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed arguments, no shell.
        [sys.executable, "-m", "stilyagi", *arguments],
        cwd=_root(state),
        env=python_module_environment(),
        capture_output=True,
        check=False,
    )
    state.setdefault("runs", []).append(completed)
    state["last_run"] = completed
    return completed


def _last_run(state: MarkdownInspectionState) -> subprocess.CompletedProcess[bytes]:
    """Return the most recent process result after asserting it exists."""
    completed = state.get("last_run")
    assert completed is not None, "expected the scenario to run the CLI"
    return completed


@given(
    "a project with one Markdown file and inherited lint selection",
    target_fixture="markdown_inspection_state",
)
def project_with_inherited_selection(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Prepare a target and an inherited rule selection in project config."""
    _write_source(markdown_inspection_state, "notes.md", b"# Notes\n")
    (_root(markdown_inspection_state) / "stilyagi.toml").write_text(
        '[lint]\nselect = ["MD001"]\n',
        encoding="utf-8",
    )
    return markdown_inspection_state


@when("I inspect the selection with an extra rule")
def inspect_selection_with_cli_override(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Inspect the effective rule selection and its winning source."""
    _run_cli(
        markdown_inspection_state,
        "config",
        "lint.select",
        "--target",
        "notes.md",
        "--select",
        "STY001",
        "--extend-select",
        "DOC001",
        "--output-format",
        "json",
    )


@then("JSON reports the combined value and config origin")
def json_reports_selection_and_origin(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Check the effective selection and its exact configuration provenance."""
    completed = _last_run(markdown_inspection_state)
    payload = json.loads(completed.stdout)
    config_path = (_root(markdown_inspection_state) / "stilyagi.toml").resolve()

    assert completed.returncode == 0, "expected config inspection to succeed"
    assert payload["value"] == ["STY001", "DOC001"], (
        "expected the flag selection and extension"
    )
    assert payload["origins"]["lint.select"] == {
        "kind": "flag",
        "source_file": str(config_path),
        "cli_overridden": True,
    }, "expected the resolved config file and CLI flag provenance"


@given(
    "a project with two Markdown files containing Unicode and CRLF",
    target_fixture="markdown_inspection_state",
)
def project_with_unicode_crlf_markdown(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Create two source files that exercise identity and line-ending fidelity."""
    _write_source(
        markdown_inspection_state,
        "docs/guide.md",
        "# Café\r\n\r\nGuide text.\r\n".encode(),
    )
    _write_source(
        markdown_inspection_state,
        "docs/appendix.mdc",
        "# Zażółć\r\n\r\nAppendix text.\r\n".encode(),
    )
    return markdown_inspection_state


@when("I dump both files as IR")
def dump_both_markdown_files(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Dump the two prepared operands through the Python module entry point."""
    source_paths = tuple(markdown_inspection_state["sources"])
    _run_cli(markdown_inspection_state, "dump-ir", *source_paths)


@then("the output is one array of canonical documents")
def output_is_one_array_of_documents(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Require one parseable array with the expected source identities."""
    completed = _last_run(markdown_inspection_state)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, "expected multi-file IR dumping to succeed"
    assert isinstance(payload, list), "expected multiple documents in one JSON array"
    assert sorted(item["document"]["path"] for item in payload) == [
        "docs/appendix.mdc",
        "docs/guide.md",
    ], "expected canonical IR identity for both requested documents"
    assert completed.stdout.endswith(b"\n"), "expected newline-terminated JSON"


@then("the source bytes are unchanged")
def source_bytes_are_unchanged(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Ensure read-only inspection leaves every source file byte-identical."""
    root = _root(markdown_inspection_state)
    for relative_path, original in markdown_inspection_state["sources"].items():
        assert (root / relative_path).read_bytes() == original, (
            f"expected {relative_path} to remain byte-identical"
        )


@given(
    "a project with a readable and an invalid UTF-8 Markdown file",
    target_fixture="markdown_inspection_state",
)
def project_with_invalid_utf8_input(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Prepare one readable operand followed by a file that cannot be decoded."""
    _write_source(markdown_inspection_state, "a-readable.md", b"# Readable\n")
    _write_source(markdown_inspection_state, "z-invalid.md", b"# Invalid \xff\n")
    return markdown_inspection_state


@then("dump-ir exits two without writing stdout")
def dump_ir_failure_is_atomic(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Require a later input failure to leave no partial JSON on stdout."""
    completed = _last_run(markdown_inspection_state)

    assert completed.returncode == 2, "expected unreadable input to exit two"
    assert completed.stdout == b"", "expected no partial JSON after an input failure"
    assert b"z-invalid.md" in completed.stderr, (
        "expected the failing reported path in the error"
    )


@given(
    "a project with one clean Markdown file",
    target_fixture="markdown_inspection_state",
)
def project_with_clean_markdown(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Prepare a clean document whose extraction can be reused."""
    _write_source(markdown_inspection_state, "notes.md", b"# Notes\n")
    return markdown_inspection_state


@when("I check it cold, warm, and with cache bypassed")
def check_cold_warm_and_bypassed(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Run three independent CLI processes against the same source bytes."""
    _run_cli(markdown_inspection_state, "check", "--verbose", "notes.md")
    _run_cli(markdown_inspection_state, "check", "--verbose", "notes.md")
    _run_cli(
        markdown_inspection_state,
        "check",
        "--verbose",
        "--no-cache",
        "notes.md",
    )


@then("the checks have equal output and report miss, hit, and bypass")
def cache_runs_agree_and_report_counters(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Assert check parity and observable cold, warm, and bypass counters."""
    runs = markdown_inspection_state["runs"]
    assert len(runs) == 3, "expected three isolated CLI invocations"
    cold, warm, bypassed = runs

    assert all(run.returncode == 0 for run in runs), "expected each clean check to pass"
    assert cold.stdout == warm.stdout == bypassed.stdout, (
        "cache selection must not change check output"
    )
    assert "cache_misses=1" in cold.stderr.decode(), "expected one cold extraction miss"
    assert "cache_hits=1" in warm.stderr.decode(), "expected one warm extraction hit"
    assert "cache_bypasses=1" in bypassed.stderr.decode(), (
        "expected no-cache to report its persistent-storage bypass"
    )


@given(
    "a project with cached YAML-frontmatter Markdown",
    target_fixture="markdown_inspection_state",
)
def project_with_cached_frontmatter(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Populate the cache for a source-backed YAML frontmatter document."""
    _write_source(
        markdown_inspection_state,
        "notes.mdc",
        b"---\ntitle: Before\n---\n# Body\r\n",
    )
    completed = _run_cli(markdown_inspection_state, "check", "--verbose", "notes.mdc")
    assert completed.returncode == 0, "expected the cold frontmatter check to pass"
    assert b"cache_misses=1" in completed.stderr, "expected a cold extraction miss"
    return markdown_inspection_state


@when("I extend its frontmatter without changing the body")
def extend_frontmatter_without_changing_body(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Add a metadata line, then check and dump the updated source in processes."""
    path = _root(markdown_inspection_state) / "notes.mdc"
    original = path.read_bytes()
    body = b"# Body\r\n"
    assert original.endswith(body), "expected a stable body suffix"
    updated = original.replace(b"---\n# Body", b"summary: Longer\n---\n# Body", 1)
    assert updated.endswith(body), "frontmatter edits must not change the body"
    path.write_bytes(updated)
    markdown_inspection_state["sources"]["notes.mdc"] = updated
    _run_cli(markdown_inspection_state, "check", "--verbose", "notes.mdc")
    _run_cli(markdown_inspection_state, "dump-ir", "notes.mdc")


@then("the changed check misses and dump spans match current bytes")
def changed_frontmatter_misses_and_dump_spans_match(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Validate fresh cache selection and body spans in actual CLI output."""
    runs = markdown_inspection_state["runs"]
    assert len(runs) == 3, "expected initial check, changed check, and dump processes"
    changed_check, dump = runs[-2:]
    source = markdown_inspection_state["sources"]["notes.mdc"]

    assert changed_check.returncode == 0, "expected the changed check to pass"
    assert b"cache_misses=1" in changed_check.stderr, (
        "frontmatter-only changes must invalidate extraction"
    )
    assert dump.returncode == 0, "expected the changed IR dump to pass"

    payload = json.loads(dump.stdout)
    assert payload["document"]["content_hash"] == (
        "sha256:" + hashlib.sha256(source).hexdigest()
    ), "the IR hash must describe the complete updated source"
    body_region = next(
        region for region in payload["regions"] if region["kind"] == "heading"
    )
    body_segment = next(
        segment for segment in body_region["segments"] if segment["source"] is not None
    )
    span = body_segment["source"]
    assert (
        source[span["byte_start"] : span["byte_end"]].decode("utf-8")
        == (body_segment["text"])
    ), "the dumped heading span must re-slice the updated source bytes"
    frontmatter = next(
        region for region in payload["regions"] if region["kind"] == "frontmatter"
    )
    assert frontmatter["text"].startswith("---\ntitle: Before\nsummary: Longer\n---"), (
        "the dump must expose the updated whole-block frontmatter region"
    )
