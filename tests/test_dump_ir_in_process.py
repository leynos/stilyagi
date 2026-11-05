"""In-process command branches for canonical Markdown IR inspection.

The end-to-end suite drives `dump-ir` through a subprocess, so the parent
process never imports the command's own modules and their branching stays
invisible to the coverage ratchet. These tests exercise the same boundaries
directly, keeping the command's fault handling measured.
"""

import errno
import json
import pathlib
import typing as typ

from stilyagi import cli_dump_ir, config, discovery, model
from stilyagi.check_inputs import CheckInput
from stilyagi.cli_args import DumpIrOptions

from tests.support.dump_ir_harness import run_dump_ir

if typ.TYPE_CHECKING:
    import pytest


def test_dump_ir_emits_one_document_in_process(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit one canonical IR object without leaving partial output on failure."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 0, "one Markdown input must extract successfully"
    assert not error, "successful extraction must stay quiet on stderr"
    payload = json.loads(output)
    assert payload["document"]["path"] == "notes.md", (
        "the emitted IR must report its source identity"
    )
    assert output.endswith(b"\n"), "canonical JSON must end with a newline"


def test_dump_ir_emits_several_documents_in_process(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frame multiple canonical documents as one ordered JSON array."""
    (tmp_path / "a.md").write_text("# Alpha\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Beta\n", encoding="utf-8")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 0, "Markdown discovery must succeed"
    assert not error, "successful discovery must stay quiet on stderr"
    payload = json.loads(output)
    assert [document["document"]["path"] for document in payload] == [
        "a.md",
        "b.md",
    ], "the array must preserve the discovered order"


def test_dump_ir_emits_an_empty_array_in_process(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit a valid empty JSON array when discovery finds no Markdown."""
    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 0, "empty discovery is a successful invocation"
    assert not error, "empty discovery must stay quiet on stderr"
    assert output == b"[]\n", "empty discovery must emit a bare array literal"


def test_dump_ir_reads_stdin_with_its_reported_name(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emit the piped bytes' IR under the reported stdin filename."""
    exit_code, output, error = run_dump_ir(
        tmp_path,
        monkeypatch,
        "-",
        stdin_text="# Piped\n",
        stdin_filename="piped.mdc",
    )

    assert exit_code == 0, "valid stdin Markdown must extract"
    assert not error, "successful stdin extraction must stay quiet on stderr"
    assert json.loads(output)["document"]["path"] == "piped.mdc", (
        "stdin IR must report the filename supplied by the caller"
    )


def test_dump_ir_requires_a_stdin_filename(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject piped bytes that carry no Markdown reporting identity."""
    exit_code, output, error = run_dump_ir(
        tmp_path, monkeypatch, "-", stdin_text="# Piped\n"
    )

    assert exit_code == 2, "stdin without a filename is an invalid invocation"
    assert not output, "a rejected invocation must emit no JSON"
    assert "--stdin-filename" in error, "the error must name the missing option"


def test_dump_ir_requires_a_markdown_stdin_filename(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a stdin reporting identity that has no Markdown extractor."""
    exit_code, output, error = run_dump_ir(
        tmp_path,
        monkeypatch,
        "-",
        stdin_text="print('hi')\n",
        stdin_filename="module.py",
    )

    assert exit_code == 2, "a non-Markdown stdin filename is invalid"
    assert not output, "a rejected invocation must emit no JSON"
    assert "must name Markdown" in error, "the error must explain the requirement"


def test_dump_ir_rejects_a_non_markdown_explicit_file_in_process(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an explicitly named file that has no Markdown extractor."""
    (tmp_path / "module.py").write_text("print('hi')\n", encoding="utf-8")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "module.py")

    assert exit_code == 2, "an explicit non-Markdown file is invalid"
    assert not output, "a rejected invocation must emit no JSON"
    assert "unsupported explicit file" in error, (
        "the error must identify the unsupported explicit file"
    )


def test_dump_ir_reports_a_discovery_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report the first discovery failure without emitting any JSON."""
    failure = discovery.DiscoveryFailure(
        path=tmp_path / "broken",
        error=PermissionError(errno.EACCES, "denied"),
    )
    result = discovery.DiscoveryResult(
        files=(),
        skipped_files=0,
        failures=(failure,),
        notices=(),
    )
    monkeypatch.setattr(
        cli_dump_ir.discovery,
        "discover_files_with_summary",
        lambda *_args, **_kwargs: result,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 2, "a discovery failure is an operational error"
    assert not output, "a failed discovery must emit no JSON"
    assert b"cannot discover" not in output, "the failure belongs on stderr"
    assert "cannot discover" in error, "the error must describe the discovery fault"


def test_dump_ir_reports_a_missing_target_notice(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turn a missing explicit target into a command error."""
    result = discovery.DiscoveryResult(
        files=(),
        skipped_files=0,
        failures=(),
        notices=(
            discovery.DiscoveryNotice(
                reason="missing_or_unsupported_target",
                path=pathlib.Path("missing.md"),
            ),
        ),
    )
    monkeypatch.setattr(
        cli_dump_ir.discovery,
        "discover_files_with_summary",
        lambda *_args, **_kwargs: result,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "missing.md")

    assert exit_code == 2, "a missing target is an invalid invocation"
    assert not output, "a rejected invocation must emit no JSON"
    assert "target does not exist" in error, "the error must name the missing target"


def test_dump_ir_reports_a_notice_without_a_path(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a discovery notice that carries no path to describe."""
    result = discovery.DiscoveryResult(
        files=(),
        skipped_files=0,
        failures=(),
        notices=(discovery.DiscoveryNotice(reason="missing_or_unsupported_target"),),
    )
    monkeypatch.setattr(
        cli_dump_ir.discovery,
        "discover_files_with_summary",
        lambda *_args, **_kwargs: result,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 2, "a pathless notice is an operational error"
    assert not output, "a rejected invocation must emit no JSON"
    assert "without a path" in error, "the error must describe the malformed notice"


def test_dump_ir_reports_an_unreadable_source(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a source whose bytes cannot be decoded as Markdown."""
    (tmp_path / "notes.md").write_bytes(b"# Invalid \xff\n")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "undecodable source bytes are an operational error"
    assert not output, "an unreadable source must emit no JSON"
    assert "cannot read notes.md" in error, "the error must name the unreadable source"


def test_dump_ir_reports_an_unsupported_config_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an unregistered explicit target notice from discovery."""
    result = discovery.DiscoveryResult(
        files=(),
        skipped_files=0,
        failures=(),
        notices=(
            discovery.DiscoveryNotice(
                reason="unregistered_explicit_file",
                path=pathlib.Path("odd.md"),
            ),
        ),
    )
    monkeypatch.setattr(
        cli_dump_ir.discovery,
        "discover_files_with_summary",
        lambda *_args, **_kwargs: result,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 2, "an unregistered explicit file is invalid"
    assert not output, "a rejected invocation must emit no JSON"
    assert "odd.md" in error, "the error must name the unregistered target"


def test_dump_ir_reports_a_missing_canonical_ir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an extractor that returns no canonical IR for its input."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")
    monkeypatch.setattr(
        cli_dump_ir.CacheExtractionService,
        "extract",
        lambda _self, _request: typ.cast(
            "object", _ExtractionResult(canonical_json=None)
        ),
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "a missing canonical result is an operational error"
    assert not output, "a missing canonical result must emit no JSON"
    assert "returned no canonical IR" in error, (
        "the error must describe the missing extractor result"
    )


def test_dump_ir_reports_an_extraction_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an extractor that rejects its own input."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    def refuse_extraction(_self: object, _request: object) -> typ.NoReturn:
        """Fail the bridge extraction for the discovered input."""
        message = "bridge refused the document"
        raise ValueError(message)

    monkeypatch.setattr(
        cli_dump_ir.CacheExtractionService, "extract", refuse_extraction
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "an extraction failure is an operational error"
    assert not output, "an extraction failure must emit no JSON"
    assert "cannot extract notes.md" in error, (
        "the error must name the input and the extraction failure"
    )


def test_dump_ir_reports_a_config_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an invalid project configuration before any extraction."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    def refuse_config(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Reject every configuration resolution for the invocation."""
        message = "cannot read stilyagi.toml"
        raise config.ConfigError(message)

    monkeypatch.setattr(
        cli_dump_ir.config.ConfigResolver,
        "resolve_config_for_path",
        refuse_config,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "an invalid configuration is an operational error"
    assert not output, "a configuration failure must emit no JSON"
    assert "cannot read stilyagi.toml" in error, (
        "the error must carry the configuration failure detail"
    )


def test_dump_ir_rejects_stdin_mixed_with_a_file_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject `-` combined with any file operand."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    exit_code, output, error = run_dump_ir(
        tmp_path, monkeypatch, "-", "notes.md", stdin_text="# Piped\n"
    )

    assert exit_code == 2, "mixing stdin with a file target is invalid"
    assert not output, "a rejected invocation must emit no JSON"
    assert "stdin target cannot be combined" in error, (
        "the error must explain the operand conflict"
    )


class _ExtractionResult:
    """Stand in for one cache extraction result with a chosen IR payload."""

    def __init__(self, canonical_json: str | None) -> None:
        """Hold the canonical JSON the extractor would have produced."""
        self.canonical_json = canonical_json


def test_dump_ir_extracts_an_explicit_markdown_check_input(
    tmp_path: pathlib.Path,
) -> None:
    """Extract one Markdown input whose exact identity was chosen by the caller."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")
    context = cli_dump_ir._ExtractionContext(
        DumpIrOptions(targets=("notes.md",)),
        config.ConfigResolver(),
        cli_dump_ir.CacheExtractionService(
            cli_dump_ir.CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version=cli_dump_ir.PACKAGE_VERSION,
                no_cache=True,
            )
        ),
    )
    try:
        canonical = cli_dump_ir._extract_document(
            CheckInput(
                reported_path="notes.md",
                resolved_path=tmp_path / "notes.md",
                syntax=model.Syntax.MARKDOWN,
            ),
            context,
        )
    finally:
        context.cache.close()

    assert json.loads(canonical)["document"]["path"] == "notes.md", (
        "one explicit input must extract to its own canonical document"
    )
