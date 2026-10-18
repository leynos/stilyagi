"""Hold `build_tools.py check` to its actionable failures.

Each case runs the script as a subprocess whose `PATH` holds only cmd-mox
shims, so a real `mold` on the machine cannot answer a missing-tool case.
"""

import typing as typ

import pytest

from tests.support.build_tools_harness import (
    CHANNEL,
    HOST,
    MOLD_BANNER,
    build_tools,
    commands,
    run_script,
    rustup_replies,
    with_working_toolchain,
    write_pins,
)

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox


@pytest.fixture
def pins(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Return fixture pin files naming the pinned channel and mold release."""
    return write_pins(tmp_path)


def test_check_passes_when_mold_and_toolchain_match_their_pins(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """The positive control: matching mold, installed toolchain and components."""
    with_working_toolchain(cmd_mox)

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "mold 2.41.0 available" in result.stderr, result.stderr


def test_check_fails_with_an_install_hint_when_mold_is_missing(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """No mold on `PATH` is an actionable error, not a linker failure later."""
    cmd_mox.stub("rustup").runs(rustup_replies())

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "mold 2.41.0 is not usable" in result.stderr, result.stderr
    assert "make install-build-tools" in result.stderr, result.stderr


def test_check_fails_when_mold_drifts_from_its_pin(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """An advisory pin is not a pin: a different mold version fails."""
    cmd_mox.stub("mold").returns(stdout="mold 2.40.0 (x)\n")
    cmd_mox.stub("rustup").runs(rustup_replies())

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "mold 2.40.0 does not match the pin 2.41.0" in result.stderr, result.stderr


def test_check_fails_when_mold_cannot_report_its_version(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """A mold that exits non-zero is broken, not drifted."""
    cmd_mox.stub("mold").returns(exit_code=1)
    cmd_mox.stub("rustup").runs(rustup_replies())

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "is not usable" in result.stderr, result.stderr


def test_check_fails_when_the_pinned_toolchain_is_not_installed(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """A missing nightly is reported by name with the install command."""
    cmd_mox.stub("mold").returns(stdout=MOLD_BANNER)
    cmd_mox.stub("rustup").returns(stdout=f"stable-{HOST} (default)\n")

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert f"toolchain {CHANNEL} is not installed" in result.stderr, result.stderr


def test_check_fails_when_a_pinned_component_is_missing(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """The Cranelift component is part of the pin, so its absence fails."""
    cmd_mox.stub("mold").returns(stdout=MOLD_BANNER)
    cmd_mox.stub("rustup").runs(
        rustup_replies(installed_components=("clippy", "rustfmt"))
    )

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "lacks components: rustc-codegen-cranelift-preview" in result.stderr, (
        result.stderr
    )


def test_check_fails_when_rustup_is_absent(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """Without rustup nothing can select the pinned nightly."""
    cmd_mox.stub("mold").returns(stdout=MOLD_BANNER)

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "rustup not found on PATH" in result.stderr, result.stderr


def test_check_reports_every_problem_in_one_pass(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """Both halves run, so a developer fixes everything in one go."""
    cmd_mox.stub("rustup").returns(stdout=f"stable-{HOST} (default)\n")

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "mold 2.41.0 is not usable" in result.stderr, result.stderr
    assert f"toolchain {CHANNEL} is not installed" in result.stderr, result.stderr


def test_check_skips_mold_off_linux(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """Mold is Linux-only, so another platform passes without it."""
    cmd_mox.stub("rustup").runs(rustup_replies())

    result = run_script(cmd_mox, "check", pins, tmp_path, "--system", "darwin")

    assert result.returncode == 0, result.stderr
    assert "mold" not in commands(cmd_mox), "expected 'mold' not in commands(cmd_mox)"


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(("", "empty version pin"), id="blank"),
        pytest.param(("2.41.0\n2.42.0\n", "expected one line"), id="multi_line"),
        pytest.param(("2.4 1.0\n", "contains whitespace"), id="inner_space"),
    ],
)
def test_a_malformed_pin_is_refused_not_repaired(
    case: tuple[str, str],
    cmd_mox: CmdMox,
    pins: dict[str, pathlib.Path],
    tmp_path: pathlib.Path,
) -> None:
    """A stray space must not become `2.41.0` by deleting whitespace."""
    content, expected = case
    pins["version"].write_text(content, encoding="utf-8")
    with_working_toolchain(cmd_mox)

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert expected in result.stderr, result.stderr


def test_a_missing_pin_file_is_reported(
    cmd_mox: CmdMox, pins: dict[str, pathlib.Path], tmp_path: pathlib.Path
) -> None:
    """An absent pin names the file."""
    pins["version"].unlink()
    with_working_toolchain(cmd_mox)

    result = run_script(cmd_mox, "check", pins, tmp_path)

    assert result.returncode == 1, result.stderr
    assert "missing version pin" in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("name", "installed", "expected"),
    [
        pytest.param("clippy", [f"clippy-{HOST}"], True, id="plain_component"),
        pytest.param(
            "rustc-codegen-cranelift-preview",
            [f"rustc-codegen-cranelift-{HOST}"],
            True,
            id="preview_suffix_dropped",
        ),
        pytest.param("clippy", [f"rustfmt-{HOST}"], False, id="other_component"),
        pytest.param(
            "rustc", [f"rustc-codegen-cranelift-{HOST}"], False, id="prefix_collision"
        ),
        pytest.param("rust-analyzer", [], False, id="nothing_installed"),
    ],
)
def test_component_names_match_rustups_installed_list(
    *, name: str, installed: list[str], expected: bool
) -> None:
    """Manifest spellings map onto `rustup component list --installed`."""
    assert build_tools.component_present(name, installed) is expected, (
        "expected build_tools.component_present(name, installed) is expected"
    )
