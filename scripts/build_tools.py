#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts>=5.2,<6", "cuprum==0.1.0"]
# ///
"""Install and check the build tools behind the development build standard.

``install`` downloads the pinned ``mold`` release, verifies it against
``tools/mold/SHA256SUMS``, unpacks it under the build-tools prefix, and then
installs the nightly toolchain (with its components) that
``rust-toolchain.toml`` pins. ``check`` is the fast preflight the Make routes
run before compilation: it fails with an actionable message when ``mold`` or
the toolchain is missing or does not match its pin, rather than letting Cargo
fail deep inside a link step or silently build a different shape.

Nothing here touches the release, packaging, coverage or Whitaker routes. The
tools are installed everywhere the suite can reach the preflight, but only the
development routes use them to compile.

Examples
--------
Install the tools, then verify them::

    make install-build-tools
    make check-build-tools
"""

import dataclasses as dc
import pathlib
import platform
import sys
import tempfile
import typing as typ

import cyclopts
from build_tools_pins import (
    BuildToolsError,
    component_present,
    expected_checksum,
    read_pin,
    read_toolchain,
    verify_archive,
)
from cuprum import sh
from cuprum.catalogue import ProgramCatalogue, ProjectSettings
from cuprum.program import Program
from cyclopts import App, Parameter

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]

CURL = Program("curl")
TAR = Program("tar")
RUSTUP = Program("rustup")
MOLD = Program("mold")

#: The only executables this script may run.
CATALOGUE = ProgramCatalogue(
    projects=(
        ProjectSettings(
            name="build-tools",
            programs=(CURL, TAR, RUSTUP, MOLD),
            documentation_locations=("docs/developers-guide.md",),
            noise_rules=(),
        ),
    )
)


_MOLD_BANNER_FIELDS: typ.Final = 2

_MACHINE_TO_MOLD_ARCH: typ.Final = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


@Parameter(name="*")
@dc.dataclass(frozen=True, slots=True)
class Layout:
    """Where the pins live and where the tools are installed.

    Every field has a ``BUILD_TOOLS_<NAME>`` environment variable, so the
    Make targets and the tests redirect the script without editing it.
    """

    prefix: pathlib.Path = pathlib.Path.home() / ".local"
    mold_version_file: pathlib.Path = REPOSITORY_ROOT / "tools/mold/VERSION"
    mold_sha256sums_file: pathlib.Path = REPOSITORY_ROOT / "tools/mold/SHA256SUMS"
    toolchain_file: pathlib.Path = REPOSITORY_ROOT / "rust-toolchain.toml"
    release_base_url: str = "https://github.com/rui314/mold/releases/download"
    # Download bounds: a stall detector rather than a deadline, so a slow but
    # progressing link is not punished while a dead one cannot hang the target.
    connect_timeout: int = 15
    min_bytes_per_second: int = 1024
    stall_seconds: int = 60
    # Host description, overridable so tests can exercise other platforms.
    system: str = ""
    machine: str = ""


def note(message: str) -> None:
    """Write one `build-tools:` diagnostic to standard error."""
    print(f"build-tools: {message}", file=sys.stderr)


def is_linux(layout: Layout) -> bool:
    """Return whether the host can use mold, which ships for Linux only."""
    return (layout.system or sys.platform).startswith("linux")


def mold_arch(layout: Layout) -> str:
    """Return the architecture name of the host's mold tarball.

    Returns
    -------
    str
        The architecture as mold's release tarballs spell it.

    Raises
    ------
    BuildToolsError
        If mold publishes no tarball for this machine.
    """
    machine = (layout.machine or platform.machine()).lower()
    try:
        return _MACHINE_TO_MOLD_ARCH[machine]
    except KeyError:
        message = f"unsupported architecture for the pinned mold release: {machine}"
        raise BuildToolsError(message) from None


def _run(program: Program, *args: str, echo: bool = False) -> sh.CommandResult:
    """Run one catalogued program and return its result without raising."""
    return sh.make(program, catalogue=CATALOGUE)(*args).run_sync(echo=echo)


def installed_mold_version() -> str | None:
    """Return the version of the mold on `PATH`, or None if it cannot run."""
    try:
        result = _run(MOLD, "--version")
    except FileNotFoundError:
        return None
    # `mold --version` prints e.g. "mold 2.41.0 (compatible with GNU ld)".
    fields = (result.stdout or "").split()[:2]
    return fields[1] if result.ok and len(fields) == _MOLD_BANNER_FIELDS else None


def check_mold(layout: Layout) -> list[str]:
    """Return the problems with the linker half of the prerequisites."""
    if not is_linux(layout):
        host = layout.system or sys.platform
        note(f"mold is Linux-only; the default {host} linker is used")
        return []
    pinned = read_pin(layout.mold_version_file)
    installed = installed_mold_version()
    if installed is None:
        return [
            f"mold {pinned} is not usable on PATH (missing, or has no version)",
            "install it with: make install-build-tools",
        ]
    if installed != pinned:
        return [
            f"mold {installed} does not match the pin {pinned}",
            "run make install-build-tools to match",
        ]
    note(f"mold {installed} available")
    return []


def check_toolchain(layout: Layout) -> list[str]:
    """Return the problems with the toolchain half of the prerequisites."""
    pin = read_toolchain(layout.toolchain_file)
    try:
        listed = _run(RUSTUP, "toolchain", "list")
    except FileNotFoundError:
        return [
            "rustup not found on PATH; it is required to select the pinned nightly",
            "install it from https://rustup.rs",
        ]
    if not any(
        line.startswith(pin.channel) for line in (listed.stdout or "").splitlines()
    ):
        return [
            f"toolchain {pin.channel} is not installed",
            "install it with: make install-build-tools",
        ]
    components = _run(
        RUSTUP, "component", "list", "--installed", "--toolchain", pin.channel
    )
    entries = (components.stdout or "").split()
    missing = [name for name in pin.components if not component_present(name, entries)]
    if missing:
        return [
            f"toolchain {pin.channel} lacks components: {', '.join(missing)}",
            "install them with: make install-build-tools",
        ]
    note(f"toolchain {pin.channel} available with its components")
    return []


def _download(layout: Layout, url: str, destination: pathlib.Path) -> None:
    """Fetch `url` with connect and stall bounds, or raise."""
    result = _run(
        CURL, "--fail", "--silent", "--show-error", "--location",
        "--connect-timeout", str(layout.connect_timeout),
        "--speed-limit", str(layout.min_bytes_per_second),
        "--speed-time", str(layout.stall_seconds),
        "--output", str(destination), url,
    )  # fmt: skip
    if not result.ok:
        message = f"failed to download {destination.name}"
        raise BuildToolsError(message)


def install_mold(layout: Layout) -> None:
    """Download, verify and unpack the pinned mold release into the prefix.

    Raises
    ------
    BuildToolsError
        If the download, checksum or unpacking fails.
    """
    if not is_linux(layout):
        note("mold is Linux-only; skipping, the platform linker is used instead")
        return
    version = read_pin(layout.mold_version_file)
    name = f"mold-{version}-{mold_arch(layout)}-linux.tar.gz"
    expected = expected_checksum(layout.mold_sha256sums_file, name)
    url = f"{layout.release_base_url}/v{version}/{name}"
    with tempfile.TemporaryDirectory() as scratch:
        archive = pathlib.Path(scratch) / name
        note(f"downloading {url}")
        _download(layout, url, archive)
        verify_archive(archive, expected)
        layout.prefix.mkdir(parents=True, exist_ok=True)
        # The tarball root is mold-<version>-<arch>-linux/{bin,lib,libexec};
        # stripping it merges the tree into the prefix so `bin/mold` is on PATH.
        unpacked = _run(
            TAR, "--extract", "--gzip", "--strip-components=1",
            "--directory", str(layout.prefix), "--file", str(archive),
        )  # fmt: skip
        if not unpacked.ok:
            message = f"failed to unpack {name} into {layout.prefix}"
            raise BuildToolsError(message)
    note(f"installed mold {version} into {layout.prefix}")


def install_toolchain(layout: Layout) -> None:
    """Install the pinned nightly with the components it names.

    Raises
    ------
    BuildToolsError
        If rustup is absent or the installation fails.
    """
    pin = read_toolchain(layout.toolchain_file)
    component_args = [arg for name in pin.components for arg in ("--component", name)]
    note(f"installing toolchain {pin.channel}")
    try:
        result = _run(
            RUSTUP, "toolchain", "install", pin.channel,
            "--profile", "minimal", *component_args, echo=True,
        )  # fmt: skip
    except FileNotFoundError:
        message = "rustup not found on PATH; install it from https://rustup.rs"
        raise BuildToolsError(message) from None
    if not result.ok:
        message = f"failed to install toolchain {pin.channel}"
        raise BuildToolsError(message)


app = App(
    name="build_tools",
    help=__doc__,
    config=cyclopts.config.Env("BUILD_TOOLS_", command=False),
)


@app.command
def install(layout: Layout | None = None) -> None:
    """Install the pinned mold and the pinned nightly toolchain."""
    layout = layout or Layout()
    # The linker first, so a checksum failure aborts before a toolchain download.
    install_mold(layout)
    install_toolchain(layout)
    note("ready; verify with: make check-build-tools")


@app.command
def check(layout: Layout | None = None) -> None:
    """Fail with an installation hint when a prerequisite is absent or stale."""
    layout = layout or Layout()
    # Both halves always run, so one pass reports every missing piece.
    problems = [*check_mold(layout), *check_toolchain(layout)]
    for problem in problems:
        note(problem)
    if problems:
        note("capability check failed; see the messages above")
        sys.exit(1)


def main() -> None:
    """Run the CLI, reporting a build-tools failure as one actionable line."""
    try:
        app()
    except BuildToolsError as error:
        note(str(error))
        sys.exit(1)


if __name__ == "__main__":
    main()
