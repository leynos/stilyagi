"""In-process contracts for the build-tools install orchestration.

The cross-process cases in `test_build_tools_install.py` prove ordering and the
resulting file tree. These call the orchestration directly with the catalogue
runner replaced, so each tool's argument vector is asserted whole: an ordering
case still passes while a download bound or a component is silently dropped.
"""

import dataclasses as dc
import pathlib
import typing as typ

import pytest

from tests.support.build_tools_harness import (
    CHANNEL,
    COMPONENTS,
    MOLD_ARCHIVE,
    PinWorkspace,
    build_tools,
    build_tools_environment,
    build_tools_pins,
    mold_archive,
    write_pins,
)

if typ.TYPE_CHECKING:
    from cuprum.sh import CommandResult


def _result(*, exit_code: int = 0) -> CommandResult:
    """Return a stand-in command result with the chosen exit status."""
    from cuprum.program import Program
    from cuprum.sh import CommandResult

    return CommandResult(
        program=Program("stub"),
        argv=(),
        exit_code=exit_code,
        pid=0,
        stdout="",
        stderr="",
    )


class _Runner:
    """Answer a scripted runner, recording each call's program and arguments."""

    def __init__(self, *answers: CommandResult | BaseException) -> None:
        """Queue one answer per expected call, in order."""
        self._answers = list(answers)
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(
        self,
        program: str,
        *args: str,
        echo: bool = False,
    ) -> CommandResult:
        """Return the next queued answer, recording the invocation."""
        self.calls.append((str(program), args))
        answer = self._answers.pop(0) if self._answers else _result()
        if isinstance(answer, BaseException):
            raise answer
        return answer


class _CurlServingRunner(_Runner):
    """Answer as `_Runner` does, writing the fixture archive for curl."""

    def __call__(
        self,
        program: str,
        *args: str,
        echo: bool = False,
    ) -> CommandResult:
        """Serve the pinned archive to curl, then answer as usual."""
        if str(program) == "curl":
            destination = pathlib.Path(args[args.index("--output") + 1])
            destination.write_bytes(mold_archive())
        return super().__call__(program, *args, echo=echo)


@pytest.fixture
def pins(tmp_path: pathlib.Path) -> PinWorkspace:
    """Return fixture pin files naming the pinned channel and mold release."""
    return write_pins(tmp_path)


def _layout(pins: PinWorkspace, **overrides: object) -> build_tools_environment.Layout:
    """Return a Linux layout pointing the build_tools at the fixture pins."""
    base = build_tools_environment.Layout(
        prefix=pins.root / "prefix",
        mold_version_file=pins.version,
        mold_sha256sums_file=pins.sums,
        toolchain_file=pins.toolchain,
        release_base_url="https://example.invalid/mold",
        system="linux",
        machine="x86_64",
    )
    return dc.replace(base, **overrides)


def test_install_mold_downloads_under_every_bound(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound the download by connect, rate and stall rather than a deadline."""
    layout = _layout(pins)
    runner = _CurlServingRunner(_result(), _result())
    monkeypatch.setattr(build_tools, "_run", runner)
    monkeypatch.setattr(build_tools, "verify_archive", lambda _archive, _expected: None)
    monkeypatch.setattr(build_tools, "mold_arch", lambda _layout: "x86_64")

    build_tools.install_mold(layout)

    program, args = runner.calls[0]
    assert program == "curl", "the pinned archive must be fetched with curl"
    assert args[:4] == ("--fail", "--silent", "--show-error", "--location"), (
        "curl must fail loudly and follow the release's redirects"
    )
    assert args[args.index("--connect-timeout") + 1] == str(layout.connect_timeout), (
        "the connect timeout must bound how long a dead link is chased"
    )
    assert args[args.index("--speed-limit") + 1] == str(layout.min_bytes_per_second), (
        "the speed limit must abort a transfer that has stalled"
    )
    assert args[args.index("--speed-time") + 1] == str(layout.stall_seconds), (
        "the speed window must bound how long a stall is tolerated"
    )
    assert args[-1] == f"https://example.invalid/mold/v2.41.0/{MOLD_ARCHIVE}", (
        "the release URL must name the pinned version and archive"
    )


def test_install_mold_unpacks_into_the_prefix(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Strip the tarball's root so `bin/mold` lands directly in the prefix."""
    layout = _layout(pins)
    runner = _CurlServingRunner(_result(), _result())
    monkeypatch.setattr(build_tools, "_run", runner)
    monkeypatch.setattr(build_tools, "verify_archive", lambda _archive, _expected: None)

    build_tools.install_mold(layout)

    program, args = runner.calls[1]
    assert program == "tar", "the verified archive must be unpacked with tar"
    assert args[:3] == ("--extract", "--gzip", "--strip-components=1"), (
        "the unpack must strip the archive root so bin/ lands in the prefix"
    )
    assert args[args.index("--directory") + 1] == str(layout.prefix), (
        "the unpack must target the configured prefix"
    )


def test_install_mold_reports_a_failed_unpack(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report a tar failure rather than leaving a half-populated prefix."""
    layout = _layout(pins)
    runner = _CurlServingRunner(_result(), _result(exit_code=1))
    monkeypatch.setattr(build_tools, "_run", runner)
    monkeypatch.setattr(build_tools, "verify_archive", lambda _archive, _expected: None)

    with pytest.raises(build_tools_pins.BuildToolsError, match="failed to unpack"):
        build_tools.install_mold(layout)


def test_install_mold_skips_off_linux(
    pins: PinWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Skip the link-time tool where mold is not the platform linker."""
    runner = _Runner()
    monkeypatch.setattr(build_tools, "_run", runner)

    build_tools.install_mold(_layout(pins, system="darwin"))

    assert not runner.calls, "no download may run where mold is unavailable"
    assert "mold is Linux-only" in capsys.readouterr().err, (
        "the skip must say why mold is not being installed"
    )


def test_install_toolchain_passes_each_component_once(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ask rustup to install the pinned channel with the manifest's components."""
    runner = _Runner(_result())
    monkeypatch.setattr(build_tools, "_run", runner)

    build_tools.install_toolchain(_layout(pins))

    program, args = runner.calls[0]
    assert program == "rustup", "the toolchain must be installed by rustup"
    assert args[:5] == ("toolchain", "install", CHANNEL, "--profile", "minimal"), (
        "the channel and minimal profile must lead the rustup arguments"
    )
    assert list(args[5:]) == [
        item for name in COMPONENTS for item in ("--component", name)
    ], "each manifest component must be requested once, in manifest order"


def test_install_toolchain_reports_an_absent_rustup(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Map an absent rustup onto the installation hint rather than a traceback."""
    monkeypatch.setattr(build_tools, "_run", _Runner(FileNotFoundError("absent")))

    with pytest.raises(
        build_tools_pins.BuildToolsError, match="rustup not found on PATH"
    ):
        build_tools.install_toolchain(_layout(pins))


def test_install_toolchain_reports_a_failed_install(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report rustup's refusal against the channel it was asked to install."""
    monkeypatch.setattr(build_tools, "_run", _Runner(_result(exit_code=1)))

    with pytest.raises(
        build_tools_pins.BuildToolsError, match=f"failed to install toolchain {CHANNEL}"
    ):
        build_tools.install_toolchain(_layout(pins))


def test_main_reports_a_build_tools_error_as_a_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Convert a reported failure into one diagnostic and a status of 1."""

    def refuse() -> typ.NoReturn:
        """Fail the CLI with an actionable build-tool error."""
        message = "failed to download"
        raise build_tools_pins.BuildToolsError(message)

    monkeypatch.setattr(build_tools, "app", refuse)

    with pytest.raises(SystemExit) as raised:
        build_tools.main()

    assert raised.value.code == 1, "a reported failure must exit with status 1"
    assert capsys.readouterr().err.startswith("build-tools: failed to download"), (
        "the failure must be reported with the standard diagnostic prefix"
    )


def test_install_runs_the_linker_before_the_toolchain(
    pins: PinWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Install mold first, so a checksum failure precedes any toolchain download."""
    order: list[str] = []
    monkeypatch.setattr(
        build_tools, "install_mold", lambda _layout: order.append("mold")
    )
    monkeypatch.setattr(
        build_tools, "install_toolchain", lambda _layout: order.append("toolchain")
    )

    build_tools.install(_layout(pins))

    assert order == ["mold", "toolchain"], (
        "the linker must be verified before rustup downloads anything"
    )
    assert "ready; verify with: make check-build-tools" in capsys.readouterr().err, (
        "a completed install must name the command that verifies it"
    )


def test_install_defaults_to_the_standard_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the repository's own pins when the caller names no layout."""
    seen: list[object] = []
    monkeypatch.setattr(build_tools, "install_mold", seen.append)
    monkeypatch.setattr(build_tools, "install_toolchain", seen.append)

    build_tools.install(None)

    assert seen, "both halves must be attempted with a default layout"
    assert all(isinstance(item, build_tools_environment.Layout) for item in seen), (
        "a layout-less install must still target a real layout"
    )


def test_check_reports_every_problem_then_fails(
    pins: PinWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print each problem before exiting, so one pass fixes everything."""
    monkeypatch.setattr(build_tools, "check_mold", lambda _layout: ["mold missing"])
    monkeypatch.setattr(
        build_tools, "check_toolchain", lambda _layout: ["rustup missing"]
    )

    with pytest.raises(SystemExit) as raised:
        build_tools.check(_layout(pins))

    assert raised.value.code == 1, "a failed capability check must exit with status 1"
    err = capsys.readouterr().err
    assert err.splitlines() == [
        "build-tools: mold missing",
        "build-tools: rustup missing",
        "build-tools: capability check failed; see the messages above",
    ], "every problem, then the summary, must be reported in one pass"


def test_check_is_silent_when_every_prerequisite_is_present(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return normally when nothing is missing, without a failure diagnostic."""
    monkeypatch.setattr(build_tools, "check_mold", lambda _layout: [])
    monkeypatch.setattr(build_tools, "check_toolchain", lambda _layout: [])

    build_tools.check(_layout(pins))


def test_check_defaults_to_the_standard_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check the repository's own pins when the caller names no layout."""
    seen: list[object] = []
    monkeypatch.setattr(
        build_tools, "check_mold", lambda layout: seen.append(layout) or []
    )
    monkeypatch.setattr(
        build_tools, "check_toolchain", lambda layout: seen.append(layout) or []
    )

    build_tools.check(None)

    assert seen, "both halves must be checked against a default layout"
    assert all(isinstance(item, build_tools_environment.Layout) for item in seen), (
        "a layout-less check must still target a real layout"
    )
