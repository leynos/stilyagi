"""Failure-mode coverage for the `stilyagi check` command."""

from __future__ import annotations

import pathlib
import typing as typ

from stilyagi import cli, engine

if typ.TYPE_CHECKING:
    import pytest


def test_cli_run_check_maps_unreadable_utf8_files_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject non-UTF-8 Markdown files with the documented file error."""
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    _stub_discovery(monkeypatch, target)

    exit_code = cli.run_check(cli.CheckOptions(targets=("broken.md",)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "stilyagi check: failed to read " in captured.err
    assert target.as_posix() in captured.err
    assert "can't decode byte 0xff" in captured.err
    assert not captured.out


def test_cli_run_check_maps_permission_errors_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject permission failures with the documented file error."""
    target = tmp_path / "restricted.md"
    target.write_text("# Restricted\n", encoding="utf-8")
    _stub_discovery(monkeypatch, target)

    original_read_text = pathlib.Path.read_text

    def read_text(path: pathlib.Path, *args: object, **kwargs: object) -> str:
        """Raise the permission failure for the target file only."""
        if path == target:
            message = "permission denied"
            raise PermissionError(message)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)

    exit_code = cli.run_check(cli.CheckOptions(targets=("restricted.md",)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not captured.out
    assert f"stilyagi check: failed to read {target.as_posix()}: permission denied" in (
        captured.err
    )


def test_cli_run_check_maps_mid_run_disappearances_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject files removed after discovery with the documented file error."""
    target = tmp_path / "vanished.md"
    target.write_text("# Vanished\n", encoding="utf-8")
    _stub_discovery(monkeypatch, target)

    original_read_text = pathlib.Path.read_text

    def read_text(path: pathlib.Path, *args: object, **kwargs: object) -> str:
        """Remove the target before the read to emulate a race."""
        if path == target:
            target.unlink()
            message = "target disappeared during read"
            raise FileNotFoundError(message)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)

    exit_code = cli.run_check(cli.CheckOptions(targets=("vanished.md",)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not captured.out
    assert (
        f"stilyagi check: failed to read {target.as_posix()}: "
        "target disappeared during read"
    ) in captured.err


def test_cli_run_check_maps_directory_reads_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject directory inputs with the documented file error."""
    target = tmp_path / "docs"
    target.mkdir()
    _stub_discovery(monkeypatch, target)

    exit_code = cli.run_check(cli.CheckOptions(targets=("docs",)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not captured.out
    assert "stilyagi check: failed to read " in captured.err
    assert target.as_posix() in captured.err
    assert "Is a directory" in captured.err


def test_cli_run_check_maps_extractor_failures_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reject extraction failures with the documented check error."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_discovery(monkeypatch, target)
    monkeypatch.setattr(
        engine,
        "extract_document",
        lambda source, syntax: _raise_runtime_error(),
    )

    exit_code = cli.run_check(cli.CheckOptions(targets=("notes.md",)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not captured.out
    assert (
        f"stilyagi check: failed to check {target.as_posix()}: bridge exploded"
        in captured.err
    )


def test_cli_main_recovers_from_real_malformed_markdown(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Accept a malformed Markdown tree without emitting diagnostics."""
    fixture_root = pathlib.Path("tests/fixtures/corpus/markdown/malformed")
    target_root = tmp_path / "docs"
    target_root.mkdir()
    for fixture_path in sorted(fixture_root.iterdir()):
        if fixture_path.is_file():
            (target_root / fixture_path.name).write_text(
                fixture_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert not captured.err
    assert captured.out == "0 diagnostics found\n"


def _stub_discovery(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
) -> None:
    """Return one discovered file so the file-read branch stays focused."""
    discovered_file = cli.CheckInput(
        reported_path=target.name,
        resolved_path=target,
    )
    monkeypatch.setattr(
        cli,
        "_discover_targets",
        lambda targets, stdin_filename: [discovered_file],
    )


def _raise_runtime_error() -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the regression test."""
    message = "bridge exploded"
    raise RuntimeError(message)
