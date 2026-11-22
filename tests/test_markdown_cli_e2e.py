"""End-to-end subprocess coverage for Markdown-specific CLI commands."""

import json
import typing as typ

from tests.support.subprocess_env import run_python_module

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess


def test_python_module_entrypoint_dumps_canonical_markdown_ir(
    tmp_path: pathlib.Path,
) -> None:
    """Expose canonical IR and the reported path through the CLI process."""
    (tmp_path / "notes.mdc").write_text("# Notes\n", encoding="utf-8")
    completed = _run_module(tmp_path, "dump-ir", "notes.mdc")

    assert completed.returncode == 0, "expected dump-ir to succeed for an MDC file"
    payload = json.loads(completed.stdout)
    assert payload["document"]["path"] == "notes.mdc", (
        "expected the explicit Markdown path in canonical IR"
    )
    assert payload["document"]["uri"] is None, "expected no synthetic source URI"
    assert completed.stdout.endswith(b"\n"), "expected newline-terminated JSON"
    assert not completed.stderr, "expected canonical IR to leave stderr empty"


def test_python_module_entrypoint_checks_an_explicit_mdc_file(
    tmp_path: pathlib.Path,
) -> None:
    """Recognize `.mdc` as Markdown when supplied as an explicit check target."""
    (tmp_path / "notes.mdc").write_text("# Notes\n", encoding="utf-8")
    completed = _run_module(tmp_path, "check", "notes.mdc")

    assert completed.returncode == 0, "expected the explicit MDC check to succeed"
    assert completed.stdout.startswith(b"checked 1 files "), (
        "expected the explicit MDC file to be checked"
    )
    assert not completed.stderr, "expected a clean explicit check"


def test_python_module_entrypoint_checks_stdin_named_with_mdc_suffix(
    tmp_path: pathlib.Path,
) -> None:
    """Infer Markdown for stdin from a `.mdc` reported filename."""
    completed = _run_module(
        tmp_path,
        "check",
        "--stdin-filename",
        "notes.mdc",
        "-",
        stdin_bytes=b"# Notes\n",
    )

    assert completed.returncode == 0, "expected named MDC stdin to check cleanly"
    assert completed.stdout.startswith(b"checked 1 files "), (
        "expected the named stdin document to be checked"
    )
    assert not completed.stderr, "expected a clean stdin check"


def _run_module(
    cwd: pathlib.Path,
    *arguments: str,
    stdin_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run one CLI command with the checkout's package importable."""
    return run_python_module(cwd, *arguments, stdin_bytes=stdin_bytes, timeout=60)
