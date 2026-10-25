"""File-read failure coverage for the `stilyagi check` command.

Every way a discovered file can fail to become source is proved here, in one
parametrized contract: an unreadable encoding, a permission refusal, a file
that vanishes between discovery and read, a directory that discovery let
through, an extractor that raises, and a read that exhausts memory. The point
of the table is that they are *not* special-cased -- each one reaches the same
exit code and the same logged warning, because the read boundary classifies
them as one operational failure rather than six.

The arrangements are heavier than the assertions, which is why they live beside
the contract they drive rather than in a shared fixture module: several of them
substitute the error only for the target file, and a shared helper would have
to grow a parameter for which path is being broken. The tests that prove a
read *succeeded* faithfully, and that a mid-batch failure does not stop the
batch, live in `tests/test_check_files.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_read_failures.py
"""

import dataclasses as dc
import functools
import pathlib
import typing as typ

import pytest
from stilyagi import cli, engine, model

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    type _FailureSetup = cabc.Callable[
        [pathlib.Path, pytest.MonkeyPatch],
        tuple[pathlib.Path, tuple[str, ...]],
    ]


@dc.dataclass(frozen=True, slots=True)
class _InjectedReadFailure:
    """Describe one read failure injected by a file-check test."""

    filename: str
    error_factory: cabc.Callable[[], Exception]
    detail: str


@dc.dataclass(frozen=True, slots=True)
class _FailingCheckHarness:
    """Pytest collaborators required to run one failing check."""

    tmp_path: pathlib.Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]


@pytest.fixture(name="harness")
def _failing_check_harness(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _FailingCheckHarness:
    """Provide the collaborators used by the failing-check test harness."""
    return _FailingCheckHarness(tmp_path, monkeypatch, capsys)


def _run_failing_check(
    harness: _FailingCheckHarness,
    target: pathlib.Path,
    *,
    unreadable_files: int,
) -> str:
    """Run one failing check and return warnings captured on stderr."""
    _stub_discovery(harness.monkeypatch, target)

    exit_code = cli.run_check(cli.CheckOptions(targets=(target.name,)))
    captured = harness.capsys.readouterr()

    assert exit_code == 2, "expected exit_code == 2"
    # A hard file error still renders the (empty) accumulated diagnostics before
    # the exit-2 signal, rather than suppressing stdout entirely.
    assert_with_context(
        captured.out
        == (
            "checked 1 files "
            f"(0 skipped, {unreadable_files} unreadable); 0 errors, 0 warnings\n"
        ),
        "expected captured.out to report the file-read outcome",
    )
    return captured.err


def _stub_discovery(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
) -> None:
    """Return one discovered file so the file-read branch stays focused.

    Discovery is substituted at the command module's own binding, which is the
    name `cli._run_check` calls. Reaching past it to `check_targets` would
    replace a function the command never looks up and leave the real discovery
    walk in the path the test is trying to isolate.
    """
    discovered_file = cli.CheckInput(
        reported_path=target.name,
        resolved_path=target,
        syntax=model.Syntax.MARKDOWN,
    )
    monkeypatch.setattr(
        cli,
        "discover_targets",
        lambda _options, _resolver: cli.DiscoveryInputs(
            (discovered_file,),
            0,
        ),
    )


def _raise_bridge_extraction_error() -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the regression test."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)


def _patch_read_bytes_failure(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
    error_factory: cabc.Callable[[], Exception],
) -> None:
    """Make byte reads of the target file raise the supplied error."""
    original_read_bytes = pathlib.Path.read_bytes

    def read_bytes(path: pathlib.Path, *args: object, **kwargs: object) -> bytes:
        """Raise the injected failure for the target file only."""
        if path == target:
            raise error_factory()
        return original_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_bytes", read_bytes)


def _read_failure_fragments(
    target: pathlib.Path,
    detail: str,
) -> tuple[str, ...]:
    """Return the logged-warning fragments expected for one failed file read."""
    return ("stilyagi check: failed to read ", target.name, detail)


def _setup_injected_read_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: _InjectedReadFailure,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose read raises the configured failure."""
    target = tmp_path / failure.filename
    target.write_text("# Read failure\n", encoding="utf-8")
    _patch_read_bytes_failure(monkeypatch, target, failure.error_factory)
    return target, _read_failure_fragments(target, failure.detail)


def _setup_unreadable_utf8(
    tmp_path: pathlib.Path,
    _monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose bytes are not valid UTF-8."""
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    return target, _read_failure_fragments(target, "can't decode byte 0xff")


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

    _patch_read_bytes_failure(monkeypatch, target, vanish)
    # A read failure is reported against the input's *reported* path, which is
    # the command-line-relative identity the run summary and every diagnostic
    # already use -- here the bare filename, not the absolute path the walk
    # built. The typed `SourceReadError` still carries the resolved path the
    # read actually attempted; attributing the message to the reported name is
    # what lets a user match the warning to the file they asked about.
    expected = (
        f"stilyagi check: failed to read {target.name}: target disappeared during read"
    )
    return target, (expected,)


def _setup_directory_read(
    tmp_path: pathlib.Path,
    _monkeypatch: pytest.MonkeyPatch,
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
        lambda _source, _syntax, *, source_path=None: _raise_bridge_extraction_error(),
    )
    expected = f"stilyagi check: failed to check {target.name}: bridge exploded"
    return target, (expected,)


@pytest.mark.parametrize(
    ("setup_failure", "unreadable_files"),
    [
        pytest.param(_setup_unreadable_utf8, 1, id="unreadable-utf8"),
        pytest.param(
            functools.partial(
                _setup_injected_read_failure,
                failure=_InjectedReadFailure(
                    filename="restricted.md",
                    error_factory=functools.partial(
                        PermissionError, "permission denied"
                    ),
                    detail="permission denied",
                ),
            ),
            1,
            id="permission-error",
        ),
        pytest.param(_setup_mid_run_disappearance, 1, id="mid-run-disappearance"),
        pytest.param(_setup_directory_read, 1, id="directory-read"),
        pytest.param(_setup_extractor_failure, 0, id="extractor-failure"),
        pytest.param(
            functools.partial(
                _setup_injected_read_failure,
                failure=_InjectedReadFailure(
                    filename="huge.md",
                    error_factory=functools.partial(MemoryError, "read too large"),
                    detail="read too large",
                ),
            ),
            1,
            id="memory-error",
        ),
    ],
)
def test_cli_run_check_maps_file_failures_to_exit_two(
    harness: _FailingCheckHarness,
    setup_failure: _FailureSetup,
    unreadable_files: int,
) -> None:
    """Reject each documented file failure with exit code 2 and a logged warning."""
    target, expected_fragments = setup_failure(harness.tmp_path, harness.monkeypatch)

    log_messages = _run_failing_check(
        harness,
        target,
        unreadable_files=unreadable_files,
    )

    for fragment in expected_fragments:
        assert fragment in log_messages, f"expected {fragment!r} in the logged warnings"
