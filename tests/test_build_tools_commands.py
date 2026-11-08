"""In-process contracts for the build-tools install orchestration.

The cross-process cases in `test_build_tools_install.py` prove ordering and the
resulting file tree. These call the orchestration directly with the catalogue
runner replaced, so each tool's argument vector is asserted whole: an ordering
case still passes while a download bound or a component is silently dropped.
"""

import dataclasses as dc
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
)
from tests.support.build_tools_harness import (
    CurlServingRunner as _CurlServingRunner,
)
from tests.support.build_tools_harness import (
    ScriptedRunner as _Runner,
)
from tests.support.build_tools_harness import (
    command_result as _result,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


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


@pytest.fixture
def layouts_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> list[build_tools_environment.Layout]:
    """Record every layout the halves of an orchestration are handed.

    The halves are replaced by recorders, so an implementation that forgot to
    resolve a layout, or resolved two different ones, is visible as an empty or
    inconsistent list rather than hiding behind a successful run.

    Returns
    -------
    list[Layout]
        One entry per attempted half, in the order they ran.
    """
    seen: list[build_tools_environment.Layout] = []
    recorder = seen.append

    def record_and_report(layout: build_tools_environment.Layout) -> list[str]:
        """Record the layout, then report no problems for it."""
        seen.append(layout)
        return []

    monkeypatch.setattr(build_tools, "install_mold", recorder)
    monkeypatch.setattr(build_tools, "install_toolchain", recorder)
    monkeypatch.setattr(build_tools, "check_mold", record_and_report)
    monkeypatch.setattr(build_tools, "check_toolchain", record_and_report)
    return seen


@pytest.mark.parametrize("orchestrate", [build_tools.install, build_tools.check])
def test_orchestrations_default_to_the_standard_layout(
    orchestrate: cabc.Callable[[build_tools_environment.Layout | None], None],
    layouts_seen: list[build_tools_environment.Layout],
) -> None:
    """Resolve the repository's own pins when the caller names no layout."""
    orchestrate(None)

    assert [type(item) for item in layouts_seen] == [
        build_tools_environment.Layout
    ] * 2, "both halves must be attempted with one real default layout"


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
