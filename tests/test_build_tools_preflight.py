"""In-process contracts for the build-tools capability preflight.

The subprocess cases in `test_build_tools_check.py` prove the diagnostics a
developer reads. These call the same preflight in-process, where its return
value is observable: the diagnostics are a list, so the exact set of problems
reported for one host can be asserted rather than pattern-matched out of a
merged standard-error stream.
"""

import pytest

from tests.support.build_tools_harness import (
    CHANNEL,
    MOLD_BANNER,
    PinWorkspace,
    build_tools_environment,
    build_tools_pins,
)
from tests.support.build_tools_harness import (
    ScriptedRunner as _Runner,
)
from tests.support.build_tools_harness import (
    command_result as _result,
)


@pytest.mark.parametrize(
    ("stdout", "exit_code"),
    [
        pytest.param("", 0, id="silent"),
        pytest.param(MOLD_BANNER, 1, id="failed"),
    ],
)
def test_installed_mold_version_reports_nothing_without_a_usable_banner(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    exit_code: int,
) -> None:
    """Treat a silent or failing mold as absent rather than guessing a version."""
    monkeypatch.setattr(
        build_tools_environment,
        "_run",
        _Runner(_result(stdout=stdout, exit_code=exit_code)),
    )

    assert build_tools_environment.installed_mold_version() is None, (
        "a mold that cannot report a version must be reported as missing"
    )


def test_installed_mold_version_reads_the_second_banner_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the version from an ordinary `mold --version` banner."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(_result(stdout=MOLD_BANNER))
    )

    assert build_tools_environment.installed_mold_version() == "2.41.0", (
        "the banner's version field must be returned as written"
    )


def test_installed_mold_version_treats_an_absent_executable_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map a missing mold executable onto the same absent answer."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(FileNotFoundError("absent"))
    )

    assert build_tools_environment.installed_mold_version() is None, (
        "a mold absent from PATH must not raise out of the preflight"
    )


def test_check_mold_reports_a_mismatch_without_raising(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return the drift diagnostics rather than failing the preflight itself."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(_result(stdout="mold 2.40.0 (x)\n"))
    )

    problems = build_tools_environment.check_mold(
        build_tools_environment.Layout(system="linux", mold_version_file=pins.version)
    )

    assert problems == [
        "mold 2.40.0 does not match the pin 2.41.0",
        "run make install-build-tools to match",
    ], "a drifted mold must report its own version against the pin"


def test_check_mold_accepts_a_matching_version(
    pins: PinWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report no problems and confirm the match on standard error."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(_result(stdout=MOLD_BANNER))
    )

    problems = build_tools_environment.check_mold(
        build_tools_environment.Layout(system="linux", mold_version_file=pins.version)
    )

    assert problems == [], "a matching mold must leave nothing to fix"
    assert "mold 2.41.0 available" in capsys.readouterr().err, (
        "the preflight must confirm what it found"
    )


def test_check_mold_reports_an_unusable_mold(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return the install hint when mold is absent from PATH."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(FileNotFoundError("absent"))
    )

    problems = build_tools_environment.check_mold(
        build_tools_environment.Layout(system="linux", mold_version_file=pins.version)
    )

    assert problems == [
        "mold 2.41.0 is not usable on PATH (missing, or has no version)",
        "install it with: make install-build-tools",
    ], "an unusable mold must name the pin it is expected to satisfy"


def test_check_toolchain_reports_an_uninstalled_channel(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Name the pinned channel when rustup has not installed it."""
    stable = _result(stdout="stable-x86_64-unknown-linux-gnu\n")
    monkeypatch.setattr(build_tools_environment, "_run", _Runner(stable))

    problems = build_tools_environment.check_toolchain(
        build_tools_environment.Layout(toolchain_file=pins.toolchain)
    )

    assert problems == [
        f"toolchain {CHANNEL} is not installed",
        "install it with: make install-build-tools",
    ], "an absent channel must be reported rather than listed for components"


def test_check_mold_skips_the_check_off_linux(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report no problems off Linux, and say which linker is used instead."""
    runner = _Runner()
    monkeypatch.setattr(build_tools_environment, "_run", runner)

    problems = build_tools_environment.check_mold(
        build_tools_environment.Layout(system="darwin")
    )

    assert problems == [], "mold is not required outside Linux"
    assert not runner.calls, "no version probe may run where mold is unusable"
    assert "the default darwin linker is used" in capsys.readouterr().err, (
        "the skip must name the linker that is used instead"
    )


def test_check_toolchain_reports_every_missing_component(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Name each component the pinned channel is missing, in manifest order."""
    monkeypatch.setattr(
        build_tools_environment,
        "_run",
        _Runner(
            _result(stdout=f"{CHANNEL}-x86_64-unknown-linux-gnu\n"),
            _result(stdout="clippy-x86_64-unknown-linux-gnu\n"),
        ),
    )

    problems = build_tools_environment.check_toolchain(
        build_tools_environment.Layout(toolchain_file=pins.toolchain)
    )

    assert problems == [
        (
            f"toolchain {CHANNEL} lacks components: "
            "rustc-codegen-cranelift-preview, rustfmt"
        ),
        "install them with: make install-build-tools",
    ], "every missing component must be named so one install fixes them all"


def test_check_toolchain_reports_an_absent_rustup(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report an absent rustup with the page to install it from."""
    monkeypatch.setattr(
        build_tools_environment, "_run", _Runner(FileNotFoundError("absent"))
    )

    problems = build_tools_environment.check_toolchain(
        build_tools_environment.Layout(toolchain_file=pins.toolchain)
    )

    assert problems == [
        "rustup not found on PATH; it is required to select the pinned nightly",
        "install it from https://rustup.rs",
    ], "an absent rustup must be reported before any listing is attempted"


def test_check_toolchain_accepts_the_pinned_channel(
    pins: PinWorkspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report no problems when the channel and every component are present."""
    monkeypatch.setattr(
        build_tools_environment,
        "_run",
        _Runner(
            _result(stdout=f"{CHANNEL}-x86_64-unknown-linux-gnu\n"),
            _result(
                stdout="clippy-x86_64-unknown-linux-gnu\n"
                "rustc-codegen-cranelift-x86_64-unknown-linux-gnu\n"
                "rustfmt-x86_64-unknown-linux-gnu\n"
            ),
        ),
    )

    problems = build_tools_environment.check_toolchain(
        build_tools_environment.Layout(toolchain_file=pins.toolchain)
    )

    assert problems == [], "an installed toolchain must leave nothing to fix"
    assert f"toolchain {CHANNEL} available" in capsys.readouterr().err, (
        "the preflight must confirm the channel it found"
    )


def test_check_toolchain_reads_the_component_list_for_the_pinned_channel(
    pins: PinWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ask rustup about the pinned channel's components, not the default's."""
    runner = _Runner(
        _result(stdout=f"{CHANNEL}-x86_64-unknown-linux-gnu\n"),
        _result(stdout="clippy-x86_64-unknown-linux-gnu\n"),
    )
    monkeypatch.setattr(build_tools_environment, "_run", runner)

    build_tools_environment.check_toolchain(
        build_tools_environment.Layout(toolchain_file=pins.toolchain)
    )

    assert runner.calls[1][1] == (
        "component",
        "list",
        "--installed",
        "--toolchain",
        CHANNEL,
    ), "the component listing must name the channel the pin selects"


def test_the_pin_module_exports_the_component_reader() -> None:
    """Keep the component matcher reachable from the module that owns pins."""
    assert build_tools_pins.component_present(
        "clippy", ["clippy-x86_64-unknown-linux-gnu"]
    ), "component matching belongs with the pin readers that feed the preflight"
