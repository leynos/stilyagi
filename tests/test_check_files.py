"""Failure-mode coverage for the `stilyagi check` command."""

from __future__ import annotations

import pathlib
import typing as typ

import pytest
from stilyagi import cli, engine

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    _FailureSetup = cabc.Callable[
        [pathlib.Path, pytest.MonkeyPatch],
        tuple[pathlib.Path, tuple[str, ...]],
    ]


def _run_failing_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: pathlib.Path,
) -> str:
    """Run one failing check against a stubbed target and return stderr."""
    _stub_discovery(monkeypatch, target)

    exit_code = cli.run_check(cli.CheckOptions(targets=(target.name,)))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert not captured.out
    return captured.err


def _patch_read_text_failure(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
    error_factory: cabc.Callable[[], Exception],
) -> None:
    """Make reads of the target file raise the supplied error."""
    original_read_text = pathlib.Path.read_text

    def read_text(path: pathlib.Path, *args: object, **kwargs: object) -> str:
        """Raise the injected failure for the target file only."""
        if path == target:
            raise error_factory()
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)


def _read_failure_fragments(
    target: pathlib.Path,
    detail: str,
) -> tuple[str, ...]:
    """Return the stderr fragments expected for one failed file read."""
    return ("stilyagi check: failed to read ", target.as_posix(), detail)


def _setup_unreadable_utf8(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose bytes are not valid UTF-8."""
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    return target, _read_failure_fragments(target, "can't decode byte 0xff")


def _setup_permission_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose read raises a permission failure."""
    target = tmp_path / "restricted.md"
    target.write_text("# Restricted\n", encoding="utf-8")
    _patch_read_text_failure(
        monkeypatch,
        target,
        lambda: PermissionError("permission denied"),
    )
    expected = f"stilyagi check: failed to read {target.as_posix()}: permission denied"
    return target, (expected,)


def _setup_mid_run_disappearance(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file that vanishes between discovery and read."""
    target = tmp_path / "vanished.md"
    target.write_text("# Vanished\n", encoding="utf-8")

    def vanish() -> FileNotFoundError:
        """Remove the target before the read to emulate a race."""
        target.unlink()
        return FileNotFoundError("target disappeared during read")

    _patch_read_text_failure(monkeypatch, target, vanish)
    expected = (
        f"stilyagi check: failed to read {target.as_posix()}: "
        "target disappeared during read"
    )
    return target, (expected,)


def _setup_directory_read(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a directory masquerading as one discovered input."""
    target = tmp_path / "docs"
    target.mkdir()
    return target, _read_failure_fragments(target, "Is a directory")


def _setup_extractor_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a readable file whose extraction blows up in the bridge."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.setattr(
        engine,
        "extract_document",
        lambda source, syntax: _raise_runtime_error(),
    )
    expected = f"stilyagi check: failed to check {target.as_posix()}: bridge exploded"
    return target, (expected,)


@pytest.mark.parametrize(
    "setup_failure",
    [
        _setup_unreadable_utf8,
        _setup_permission_error,
        _setup_mid_run_disappearance,
        _setup_directory_read,
        _setup_extractor_failure,
    ],
    ids=[
        "unreadable-utf8",
        "permission-error",
        "mid-run-disappearance",
        "directory-read",
        "extractor-failure",
    ],
)
def test_cli_run_check_maps_file_failures_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    setup_failure: _FailureSetup,
) -> None:
    """Reject each documented file failure with exit code 2 and stderr."""
    target, expected_fragments = setup_failure(tmp_path, monkeypatch)

    stderr = _run_failing_check(monkeypatch, capsys, target)

    for fragment in expected_fragments:
        assert fragment in stderr


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
