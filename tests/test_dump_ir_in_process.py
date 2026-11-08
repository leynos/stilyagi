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

import pytest
from stilyagi import cli_dump_ir, discovery

from tests.support.dump_ir_harness import Stdin, run_dump_ir

type _NoticeReason = typ.Literal[
    "missing_or_unsupported_target",
    "unregistered_explicit_file",
]


def _report_one_notice(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reason: _NoticeReason,
    path: pathlib.Path | None = None,
) -> None:
    """Make discovery report one notice instead of walking any target."""
    result = discovery.DiscoveryResult(
        files=(),
        skipped_files=0,
        failures=(),
        notices=(discovery.DiscoveryNotice(reason=reason, path=path),),
    )
    monkeypatch.setattr(
        cli_dump_ir.discovery,
        "discover_files_with_summary",
        lambda *_args, **_kwargs: result,
    )


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
        stdin=Stdin(text="# Piped\n", filename="piped.mdc"),
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
        tmp_path, monkeypatch, "-", stdin=Stdin(text="# Piped\n")
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
        stdin=Stdin(text="print('hi')\n", filename="module.py"),
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


class _UnusableTarget(typ.NamedTuple):
    """One notice about a target the command must reject, with its diagnostic."""

    reason: _NoticeReason
    named: str
    mention: str
    message: str


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(
            _UnusableTarget(
                "missing_or_unsupported_target",
                "missing.md",
                "target does not exist",
                "a missing target is an invalid invocation",
            ),
            id="missing-target",
        ),
        pytest.param(
            _UnusableTarget(
                "unregistered_explicit_file",
                "odd.md",
                "odd.md",
                "an unregistered explicit file is invalid",
            ),
            id="unregistered-target",
        ),
    ],
)
def test_dump_ir_reports_an_unusable_explicit_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    target: _UnusableTarget,
) -> None:
    """Turn each notice about an unusable explicit target into a command error."""
    _report_one_notice(
        monkeypatch, reason=target.reason, path=pathlib.Path(target.named)
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, target.named)

    assert exit_code == 2, target.message
    assert not output, "a rejected invocation must emit no JSON"
    assert target.mention in error, "the error must name the offending target"


def test_dump_ir_reports_a_notice_without_a_path(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a discovery notice that carries no path to describe."""
    _report_one_notice(monkeypatch, reason="missing_or_unsupported_target")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, ".")

    assert exit_code == 2, "a pathless notice is an operational error"
    assert not output, "a rejected invocation must emit no JSON"
    assert "without a path" in error, "the error must describe the malformed notice"


def test_dump_ir_rejects_stdin_mixed_with_a_file_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject `-` combined with any file operand."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    exit_code, output, error = run_dump_ir(
        tmp_path, monkeypatch, "-", "notes.md", stdin=Stdin(text="# Piped\n")
    )

    assert exit_code == 2, "mixing stdin with a file target is invalid"
    assert not output, "a rejected invocation must emit no JSON"
    assert "stdin target cannot be combined" in error, (
        "the error must explain the operand conflict"
    )
