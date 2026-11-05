"""In-process contracts for the pure build-tool pin and host helpers.

`test_build_tools_install.py` and `test_build_tools_check.py` drive the build_tools
as a subprocess, so their assertions prove the messages a developer sees while
the helpers themselves stay unmeasured. These tests call the same helpers
directly: each refusal is pinned to the value or the file that caused it, and
the host readings are exercised through ``Layout`` overrides rather than the
machine this suite happens to run on.
"""

import hashlib
import typing as typ

import pytest

from tests.support.build_tools_harness import (
    CHANNEL,
    COMPONENTS,
    MOLD_ARCHIVE,
    PinWorkspace,
    build_tools_environment,
    build_tools_pins,
    mold_archive,
    write_pins,
)

if typ.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def pins(tmp_path: pathlib.Path) -> PinWorkspace:
    """Return fixture pin files naming the pinned channel and mold release."""
    return write_pins(tmp_path)


def test_read_pin_trims_one_version(pins: PinWorkspace) -> None:
    """Return the pinned version without its trailing newline."""
    assert build_tools_pins.read_pin(pins.version) == "2.41.0", (
        "a well-formed pin must read back as the bare version"
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("", "empty version pin", id="empty-file"),
        pytest.param("\n", "empty version pin", id="blank-line"),
        pytest.param("2.41.0\n2.42.0", "expected one line", id="two-lines"),
        pytest.param("2.4 1.0\n", "contains whitespace", id="inner-space"),
    ],
)
def test_read_pin_refuses_an_unusable_pin(
    pins: PinWorkspace,
    content: str,
    expected: str,
) -> None:
    """Refuse a pin rather than repair it into a different version."""
    pins.version.write_text(content, encoding="utf-8")

    with pytest.raises(build_tools_pins.BuildToolsError, match=expected):
        build_tools_pins.read_pin(pins.version)


def test_read_pin_reports_a_missing_file(tmp_path: pathlib.Path) -> None:
    """Name the absent pin file rather than surfacing a bare OSError."""
    missing = tmp_path / "VERSION"

    with pytest.raises(build_tools_pins.BuildToolsError, match="missing version pin"):
        build_tools_pins.read_pin(missing)


def test_read_toolchain_returns_the_channel_and_components(pins: PinWorkspace) -> None:
    """Read the pinned channel and every component the manifest lists."""
    pin = build_tools_pins.read_toolchain(pins.toolchain)

    assert pin.channel == CHANNEL, "the channel must survive parsing unchanged"
    assert pin.components == COMPONENTS, "the components must keep the manifest's order"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("not toml", "missing or unreadable toolchain pin", id="bad-toml"),
        pytest.param("[toolchain]\n", "no channel found", id="no-channel"),
        pytest.param('[toolchain]\nchannel = ""\n', "no channel found", id="empty"),
        pytest.param("[toolchain]\nchannel = 1\n", "no channel found", id="non-string"),
        pytest.param("channel = 'x'\n", "no channel found", id="not-a-table"),
    ],
)
def test_read_toolchain_refuses_an_unusable_manifest(
    pins: PinWorkspace,
    content: str,
    expected: str,
) -> None:
    """Refuse a manifest that cannot name the channel to install."""
    pins.toolchain.write_text(content, encoding="utf-8")

    with pytest.raises(build_tools_pins.BuildToolsError, match=expected):
        build_tools_pins.read_toolchain(pins.toolchain)


def test_read_toolchain_reports_a_missing_manifest(tmp_path: pathlib.Path) -> None:
    """Name an absent manifest instead of letting the read error escape."""
    with pytest.raises(
        build_tools_pins.BuildToolsError, match="missing or unreadable toolchain pin"
    ):
        build_tools_pins.read_toolchain(tmp_path / "rust-toolchain.toml")


def test_read_toolchain_defaults_to_no_components(pins: PinWorkspace) -> None:
    """Treat a manifest without a components list as pinning none."""
    pins.toolchain.write_text(f'[toolchain]\nchannel = "{CHANNEL}"\n', encoding="utf-8")

    pin = build_tools_pins.read_toolchain(pins.toolchain)

    assert pin.components == (), "an absent component list must not invent entries"


def test_component_present_requires_a_host_suffix() -> None:
    """Require the host suffix rustup appends, not the bare component name."""
    assert not build_tools_pins.component_present("clippy", ["clippy"]), (
        "a name without its host suffix cannot prove the component is installed"
    )


def test_expected_checksum_reads_the_unique_matching_row(pins: PinWorkspace) -> None:
    """Return the digest recorded for the pinned archive."""
    digest = hashlib.sha256(mold_archive()).hexdigest()

    assert build_tools_pins.expected_checksum(pins.sums, MOLD_ARCHIVE) == digest, (
        "the checksum list's row must be returned verbatim"
    )


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        pytest.param("", "no checksum recorded", id="absent"),
        pytest.param("only-one-field\n", "no checksum recorded", id="short-row"),
        pytest.param(
            f"{'a' * 64}  other.tar.gz\n", "no checksum recorded", id="other-name"
        ),
        pytest.param(
            f"{'a' * 64}  {MOLD_ARCHIVE}\n{'b' * 64}  {MOLD_ARCHIVE}\n",
            "2 checksums recorded",
            id="duplicated",
        ),
    ],
)
def test_expected_checksum_refuses_an_absent_or_ambiguous_row(
    pins: PinWorkspace,
    rows: str,
    expected: str,
) -> None:
    """Never guess which digest an archive should have."""
    pins.sums.write_text(rows, encoding="utf-8")

    with pytest.raises(build_tools_pins.BuildToolsError, match=expected):
        build_tools_pins.expected_checksum(pins.sums, MOLD_ARCHIVE)


def test_expected_checksum_reports_a_missing_checksum_file(
    tmp_path: pathlib.Path,
) -> None:
    """Name the absent checksum list rather than raising OSError."""
    with pytest.raises(build_tools_pins.BuildToolsError, match="missing checksum file"):
        build_tools_pins.expected_checksum(tmp_path / "SHA256SUMS", MOLD_ARCHIVE)


def test_verify_archive_accepts_a_matching_digest(tmp_path: pathlib.Path) -> None:
    """Accept an archive whose bytes hash to the pinned digest, in any case."""
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(mold_archive())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    build_tools_pins.verify_archive(archive, digest.upper())


def test_verify_archive_refuses_a_mismatched_digest(tmp_path: pathlib.Path) -> None:
    """Refuse bytes that do not hash to the pinned digest."""
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"tampered")

    expected = r"checksum mismatch for release\.tar\.gz"
    with pytest.raises(build_tools_pins.BuildToolsError, match=expected):
        build_tools_pins.verify_archive(archive, "0" * 64)


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        pytest.param("linux", True, id="linux"),
        pytest.param("linux5", True, id="linux-prefixed"),
        pytest.param("darwin", False, id="darwin"),
        pytest.param("win32", False, id="windows"),
    ],
)
def test_is_linux_reads_the_layout_override(
    *,
    system: str,
    expected: bool,
) -> None:
    """Prefer the layout's host override over the running interpreter's."""
    assert (
        build_tools_environment.is_linux(build_tools_environment.Layout(system=system))
        is expected
    ), "the platform reading must follow the configured host"


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        pytest.param("x86_64", "x86_64", id="x86-64"),
        pytest.param("AMD64", "x86_64", id="amd64-upper"),
        pytest.param("aarch64", "aarch64", id="aarch64"),
        pytest.param("arm64", "aarch64", id="arm64"),
    ],
)
def test_mold_arch_maps_each_supported_machine(machine: str, expected: str) -> None:
    """Translate a host architecture into the release's own spelling."""
    assert (
        build_tools_environment.mold_arch(
            build_tools_environment.Layout(machine=machine)
        )
        == expected
    ), "a supported machine must map onto its published archive name"


def test_mold_arch_refuses_an_unpublished_machine() -> None:
    """Refuse an architecture the pinned release does not publish."""
    with pytest.raises(
        build_tools_pins.BuildToolsError, match=r"unsupported architecture.*riscv64"
    ):
        build_tools_environment.mold_arch(
            build_tools_environment.Layout(machine="riscv64")
        )


def test_mold_arch_falls_back_to_the_platform_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read the running host when the layout names no machine."""
    monkeypatch.setattr(build_tools_environment.platform, "machine", lambda: "arm64")

    assert (
        build_tools_environment.mold_arch(build_tools_environment.Layout()) == "aarch64"
    ), "an empty layout must consult the host's own architecture"


def test_is_linux_falls_back_to_the_running_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read the running interpreter's platform when the layout names none."""
    monkeypatch.setattr(build_tools_environment.sys, "platform", "darwin")

    assert (
        build_tools_environment.is_linux(build_tools_environment.Layout()) is False
    ), "an empty layout must consult the host's own platform"
