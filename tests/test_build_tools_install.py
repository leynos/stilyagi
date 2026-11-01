"""Hold `build_tools.py install` to verified, ordered, failing-closed steps.

The journal proves what ran and in what order: a checksum failure must stop
before `tar` or `rustup` is reached.
"""

import typing as typ

import pytest

from tests.support.build_tools_harness import (
    CHANNEL,
    COMPONENTS,
    MOLD_ARCHIVE,
    PinWorkspace,
    commands,
    extract_archive,
    mold_archive,
    run_script,
    serve_archive,
    write_pins,
)

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox


@pytest.fixture
def pins(tmp_path: pathlib.Path) -> PinWorkspace:
    """Return fixture pin files naming the pinned channel and mold release."""
    return write_pins(tmp_path)


def test_install_downloads_verifies_unpacks_and_installs_the_toolchain(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """The full path, in order: curl, then tar, then rustup."""
    cmd_mox.stub("curl").runs(serve_archive(mold_archive()))
    cmd_mox.stub("tar").runs(extract_archive)
    cmd_mox.stub("rustup").returns()

    result = run_script(cmd_mox, "install", pins)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "prefix" / "bin" / "mold").exists(), (
        "expected (tmp_path / 'prefix' / 'bin' / 'mold').exists()"
    )
    assert commands(cmd_mox) == ["curl", "tar", "rustup"], (
        "expected commands(cmd_mox) == ['curl', 'tar', 'rustup']"
    )
    curl, _, rustup = tuple(cmd_mox.journal)
    assert curl.args[-1].endswith(f"/v2.41.0/{MOLD_ARCHIVE}"), (
        f"curl fetched {curl.args[-1]}"
    )
    for bound in ("--connect-timeout", "--speed-limit", "--speed-time"):
        assert bound in curl.args, "expected bound in curl.args"
    assert rustup.args[:5] == [
        "toolchain",
        "install",
        CHANNEL,
        "--profile",
        "minimal",
    ], "expected rustup.args[:5] == ['toolchain', 'install', CHANNEL, '--p..."
    assert rustup.args.count("--component") == len(COMPONENTS), (
        "expected rustup.args.count('--component') == len(COMPONENTS)"
    )


def test_install_refuses_a_checksum_mismatch_before_unpacking(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """A tampered archive stops the install: no tar, no toolchain download."""
    cmd_mox.stub("curl").runs(serve_archive(b"not the release"))
    cmd_mox.stub("tar").runs(extract_archive)
    cmd_mox.stub("rustup").returns()

    result = run_script(cmd_mox, "install", pins)

    assert result.returncode == 1, result.stderr
    assert f"checksum mismatch for {MOLD_ARCHIVE}" in result.stderr, result.stderr
    assert commands(cmd_mox) == ["curl"], "expected commands(cmd_mox) == ['curl']"
    assert not (tmp_path / "prefix").exists(), (
        "expected not (tmp_path / 'prefix').exists()"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(("", "no checksum recorded"), id="unlisted"),
        pytest.param(
            (
                f"{'a' * 64}  {MOLD_ARCHIVE}\n{'b' * 64}  {MOLD_ARCHIVE}\n",
                "2 checksums recorded",
            ),
            id="ambiguous",
        ),
    ],
)
def test_install_refuses_an_unlisted_or_ambiguous_checksum(
    case: tuple[str, str],
    cmd_mox: CmdMox,
    pins: PinWorkspace,
    tmp_path: pathlib.Path,
) -> None:
    """An artefact without exactly one digest is never downloaded."""
    rows, expected = case
    pins.sums.write_text(rows, encoding="utf-8")
    cmd_mox.stub("curl").runs(serve_archive(mold_archive()))
    cmd_mox.stub("rustup").returns()

    result = run_script(cmd_mox, "install", pins)

    assert result.returncode == 1, result.stderr
    assert expected in result.stderr, result.stderr
    assert not commands(cmd_mox), "expected not commands(cmd_mox)"


def test_install_reports_a_failed_download(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """A curl failure stops the install before anything is unpacked."""
    cmd_mox.stub("curl").returns(exit_code=22)
    cmd_mox.stub("rustup").returns()

    result = run_script(cmd_mox, "install", pins)

    assert result.returncode == 1, result.stderr
    assert f"failed to download {MOLD_ARCHIVE}" in result.stderr, result.stderr
    assert commands(cmd_mox) == ["curl"], "expected commands(cmd_mox) == ['curl']"


def test_install_reports_a_failed_toolchain_install(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """A rustup failure fails the install."""
    cmd_mox.stub("curl").runs(serve_archive(mold_archive()))
    cmd_mox.stub("tar").runs(extract_archive)
    cmd_mox.stub("rustup").returns(exit_code=1)

    result = run_script(cmd_mox, "install", pins)

    assert result.returncode == 1, result.stderr
    assert f"failed to install toolchain {CHANNEL}" in result.stderr, result.stderr


def test_install_skips_mold_off_linux_but_installs_the_toolchain(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """Off Linux only the toolchain half runs."""
    cmd_mox.stub("rustup").returns()

    result = run_script(cmd_mox, "install", pins, "--system", "darwin")

    assert result.returncode == 0, result.stderr
    assert commands(cmd_mox) == ["rustup"], "expected commands(cmd_mox) == ['rustup']"


def test_install_refuses_an_unsupported_architecture(
    cmd_mox: CmdMox, pins: PinWorkspace, tmp_path: pathlib.Path
) -> None:
    """No mold tarball exists for this machine, so nothing is downloaded."""
    cmd_mox.stub("curl").returns()

    result = run_script(cmd_mox, "install", pins, "--machine", "riscv64")

    assert result.returncode == 1, result.stderr
    assert "unsupported architecture" in result.stderr, result.stderr
    assert not commands(cmd_mox), "expected not commands(cmd_mox)"
