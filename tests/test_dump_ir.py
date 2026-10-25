"""End-to-end contracts for canonical Markdown IR inspection."""

import io
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests use a trusted local interpreter.
import sys
import typing as typ

import pytest
from stilyagi import cli_dump_ir, engine, model
from stilyagi.cli_args import DumpIrOptions
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import pathlib

    from syrupy.assertion import SnapshotAssertion


def test_dump_ir_snapshots_one_canonical_document(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Emit the Rust canonical JSON unchanged for one Markdown input."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    completed = _run_dump_ir(tmp_path, "notes.md")

    assert completed.returncode == 0, "expected one input to extract successfully"
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict), "expected one input to emit an IR object"
    assert payload["document"]["path"] == "notes.md", "expected reported source path"
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected one-document canonical IR snapshot"
    )
    assert completed.stdout.endswith(b"\n"), "expected canonical JSON newline"
    assert not completed.stderr, "expected extraction logs to stay off stderr"


def test_dump_ir_snapshots_multiple_markdown_documents(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Frame multiple sources as an ordered JSON array and include .mdc."""
    (tmp_path / "b.markdown").write_text("# Beta\n", encoding="utf-8")
    (tmp_path / "a.mdc").write_text("# Alpha\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text('"""Python docs."""\n', encoding="utf-8")

    completed = _run_dump_ir(tmp_path, ".")

    assert completed.returncode == 0, "expected Markdown discovery to succeed"
    payload = json.loads(completed.stdout)
    assert isinstance(payload, list), "expected multiple inputs to emit an array"
    assert [document["document"]["path"] for document in payload] == [
        "a.mdc",
        "b.markdown",
    ], "expected sorted Markdown paths including the component suffix"
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected multi-document canonical IR snapshot"
    )
    assert completed.stdout.endswith(b"\n"), "expected array framing newline"
    assert not completed.stderr, "expected extraction logs to stay off stderr"


def test_dump_ir_snapshots_empty_discovery_as_an_empty_array(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Give empty discovery a valid, newline-terminated JSON value."""
    completed = _run_dump_ir(tmp_path, ".")

    assert completed.returncode == 0, "expected empty discovery to succeed"
    payload = json.loads(completed.stdout)
    assert payload == [], "expected no Markdown inputs to produce an empty array"
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected empty-array snapshot"
    )
    assert not completed.stderr, "expected empty discovery to stay quiet"


def test_dump_ir_preserves_frontmatter_and_rust_canonical_bytes(
    tmp_path: pathlib.Path,
) -> None:
    """Retain Unicode, CRLF frontmatter and the bridge's exact JSON string."""
    source = "---\r\ntitle: Café\r\n---\r\n\r\n# Body\r\n"
    (tmp_path / "notes.mdc").write_bytes(source.encode("utf-8"))

    completed = _run_dump_ir(tmp_path, "notes.mdc")
    canonical_json = engine.extract_document_result(
        source,
        model.Syntax.MARKDOWN,
        source_path="notes.mdc",
    ).canonical_json

    assert completed.returncode == 0, "expected frontmatter extraction to succeed"
    assert canonical_json is not None, "expected canonical JSON from the Rust bridge"
    assert completed.stdout == canonical_json.encode("utf-8"), (
        "expected dump-ir bytes to equal the Rust serializer output"
    )
    payload = json.loads(completed.stdout)
    frontmatter = next(
        region for region in payload["regions"] if region["kind"] == "frontmatter"
    )
    assert frontmatter["segments"][0]["text"] == "---\r\ntitle: Café\r\n---", (
        "expected exact CRLF frontmatter bytes in the canonical IR"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(("-",), id="stdin-needs-filename"),
        pytest.param(("-", "-", "--stdin-filename", "notes.md"), id="duplicate-stdin"),
        pytest.param(
            ("-", "notes.md", "--stdin-filename", "notes.md"), id="mixed-inputs"
        ),
        pytest.param(("--stdin-filename", "notes.py", "-"), id="non-markdown-filename"),
    ],
)
def test_dump_ir_rejects_invalid_stdin_shapes(
    tmp_path: pathlib.Path,
    arguments: tuple[str, ...],
) -> None:
    """Reject unnamed stdin, repeated stdin and mixed stdin/file operands."""
    completed = _run_dump_ir(tmp_path, *arguments, stdin_bytes=b"# Piped\n")

    assert completed.returncode == 2, "expected invalid stdin operands to exit two"
    assert not completed.stdout, "expected usage failures to emit no partial IR"
    assert b"stilyagi dump-ir:" in completed.stderr, (
        "expected a command error on stderr"
    )


def test_dump_ir_validates_config_when_reading_stdin(tmp_path: pathlib.Path) -> None:
    """An accepted config option still reports an invalid discovered config."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")

    completed = _run_dump_ir(
        tmp_path,
        "--stdin-filename",
        "notes.md",
        "-",
        stdin_bytes=b"# Piped\n",
    )

    assert completed.returncode == 2, "expected invalid stdin config to exit two"
    assert not completed.stdout, "expected config failures to emit no IR"
    assert b"toml" in completed.stderr.lower(), "expected the invalid TOML cause"


def test_dump_ir_uses_stdin_filename_as_ir_source_identity(
    tmp_path: pathlib.Path,
) -> None:
    """Require and retain the reported Markdown filename for stdin bytes."""
    completed = _run_dump_ir(
        tmp_path,
        "--stdin-filename",
        "docs/notes.mdc",
        "-",
        stdin_bytes=b"# Piped\n",
    )

    assert completed.returncode == 0, "expected named stdin extraction to succeed"
    payload = json.loads(completed.stdout)
    assert payload["document"]["path"] == "docs/notes.mdc", (
        "expected the stdin filename to become source identity"
    )
    assert payload["document"]["uri"] is None, "expected no synthetic source URI"


def test_dump_ir_rejects_an_explicit_non_markdown_file(
    tmp_path: pathlib.Path,
) -> None:
    """Fail explicitly instead of silently omitting a requested non-Markdown file."""
    (tmp_path / "module.py").write_text('"""Docs."""\n', encoding="utf-8")

    completed = _run_dump_ir(tmp_path, "module.py")

    assert completed.returncode == 2, "expected an explicit Python file to be rejected"
    assert not completed.stdout, "expected unsupported input to emit no IR"
    assert b"module.py" in completed.stderr, (
        "expected the unsupported path in the error"
    )


def test_dump_ir_rejects_a_missing_explicit_file(tmp_path: pathlib.Path) -> None:
    """Report a missing requested input instead of treating it as empty discovery."""
    completed = _run_dump_ir(tmp_path, "missing.md")

    assert completed.returncode == 2, "expected a missing explicit input to exit two"
    assert not completed.stdout, "expected a missing input to emit no IR"
    assert b"missing.md" in completed.stderr, "expected the missing path in the error"


def test_dump_ir_buffers_output_until_all_inputs_succeed(
    tmp_path: pathlib.Path,
) -> None:
    """Do not emit the first document when a later input cannot be decoded."""
    (tmp_path / "a-valid.md").write_text("# Valid\n", encoding="utf-8")
    (tmp_path / "z-invalid.md").write_bytes(b"# Invalid \xff\n")

    completed = _run_dump_ir(tmp_path, ".")

    assert completed.returncode == 2, "expected invalid source bytes to fail"
    assert not completed.stdout, "expected failed input batches to emit no JSON"
    assert b"z-invalid.md" in completed.stderr, "expected the unreadable source path"


def test_dump_ir_reports_spool_creation_failure_before_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A temporary-storage failure is an operational error with empty stdout."""
    monkeypatch.chdir(tmp_path)

    def fail_to_create_spool(**_kwargs: object) -> typ.NoReturn:
        """Simulate an unavailable temporary-storage directory."""
        raise OSError

    monkeypatch.setattr(
        cli_dump_ir.tempfile,
        "SpooledTemporaryFile",
        fail_to_create_spool,
    )
    output = io.BytesIO()
    error = io.StringIO()

    exit_code = cli_dump_ir.run_dump_ir(
        DumpIrOptions(targets=(".",)),
        output=output,
        error=error,
    )

    assert exit_code == 2, "expected spool creation failure to exit two"
    assert output.getvalue() == b"", "expected spool creation failure to emit no JSON"
    assert error.getvalue().startswith("stilyagi dump-ir:"), (
        "expected spool creation failure on stderr"
    )


def test_dump_ir_reports_spool_write_failure_before_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spool write failure cannot expose a partial JSON value."""
    monkeypatch.chdir(tmp_path)

    class FailingSpool:
        """Minimal spool double that refuses every output write."""

        def __init__(self, **_kwargs: object) -> None:
            """Accept the same constructor options as a spooled temporary file."""

        def __enter__(self) -> FailingSpool:
            """Return the failing spool as a context manager."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the simulated spool context without cleanup work."""

        def write(self, _data: bytes) -> typ.Never:
            """Fail every attempted write."""
            raise OSError

    monkeypatch.setattr(cli_dump_ir.tempfile, "SpooledTemporaryFile", FailingSpool)
    output = io.BytesIO()
    error = io.StringIO()

    exit_code = cli_dump_ir.run_dump_ir(
        DumpIrOptions(targets=(".",)),
        output=output,
        error=error,
    )

    assert exit_code == 2, "expected spool write failure to exit two"
    assert output.getvalue() == b"", "expected spool write failure to emit no JSON"
    assert error.getvalue().startswith("stilyagi dump-ir:"), (
        "expected spool write failure on stderr"
    )


def test_dump_ir_reports_framing_spool_failure_before_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not write stdout when completed JSON cannot be framed in the spool."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")
    spool_count = 0

    class FailingFramingSpool:
        """Stand in for the final-output spool after extraction has completed."""

        def __init__(self, **_kwargs: object) -> None:
            """Accept the same constructor options as a spooled temporary file."""

        def __enter__(self) -> FailingFramingSpool:
            """Return the failing spool as a context manager."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the simulated spool context without cleanup work."""

        def write(self, _data: bytes) -> typ.Never:
            """Fail every attempted write."""
            raise cli_dump_ir.DumpIrSpoolError(
                cli_dump_ir.DumpIrSpoolErrorCode.SHORT_JSON_SPOOL_WRITE
            )

    def spool_factory(
        max_size: int,
        mode: typ.Literal["w+b"],
    ) -> typ.IO[bytes] | FailingFramingSpool:
        """Keep the document spool real and fail the final framing spool."""
        nonlocal spool_count
        assert max_size > 0, "expected a bounded spool"
        assert mode == "w+b", "expected a binary read/write spool"
        spool_count += 1
        if spool_count == 1:
            return io.BytesIO()
        return FailingFramingSpool()

    monkeypatch.setattr(cli_dump_ir.tempfile, "SpooledTemporaryFile", spool_factory)
    output = io.BytesIO()
    error = io.StringIO()

    exit_code = cli_dump_ir.run_dump_ir(
        DumpIrOptions(targets=("notes.md",)),
        output=output,
        error=error,
    )

    assert exit_code == 2, "expected framing spool failure to exit two"
    assert output.getvalue() == b"", "expected framing failure to emit no JSON"
    assert "short write to JSON spool" in error.getvalue(), (
        "expected framing spool failure detail"
    )


def _run_dump_ir(
    cwd: pathlib.Path,
    *arguments: str,
    stdin_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run one dump-ir subprocess with the checkout package importable."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, "-m", "stilyagi", "dump-ir", *arguments],
        cwd=cwd,
        env=python_module_environment(),
        input=stdin_bytes,
        capture_output=True,
        check=False,
    )
