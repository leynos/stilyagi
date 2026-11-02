"""Host configuration and capability checks for the build-tools CLI.

This internal sibling owns the shared layout, catalogued command execution,
and host preflight. Installation orchestration remains in ``build_tools.py``;
pin and checksum readers remain pure in ``build_tools_pins.py``. These helpers
are scoped to the build-tools entrypoint rather than a general command runner.
"""

import dataclasses as dc
import pathlib
import platform
import sys
import typing as typ

from build_tools_pins import (
    BuildToolsError,
    component_present,
    read_pin,
    read_toolchain,
)
from cuprum import sh
from cuprum.catalogue import ProgramCatalogue, ProjectSettings
from cuprum.program import Program
from cyclopts import Parameter

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
    """Where the build-tool pins live and where tools are installed.

    Each field can be overridden by its ``BUILD_TOOLS_<NAME>`` environment
    variable, allowing Make targets and tests to select an isolated
    layout.

    Attributes
    ----------
    prefix : pathlib.Path
        Installation prefix; defaults to ``~/.local``.
    mold_version_file : pathlib.Path
        File containing the single mold version pin.
    mold_sha256sums_file : pathlib.Path
        Checksum list for the pinned mold archive.
    toolchain_file : pathlib.Path
        Rust toolchain manifest, including required components.
    release_base_url : str
        Base URL for mold release downloads.
    connect_timeout : int
        Seconds allowed to establish a download connection.
    min_bytes_per_second : int
        Minimum transfer rate before curl treats a download as stalled.
    stall_seconds : int
        Seconds below the minimum transfer rate before curl stops.
    system : str
        Optional host-system override, primarily for tests.
    machine : str
        Optional host-architecture override, primarily for tests.

    Examples
    --------
    Override one download timeout without changing the other defaults::

        layout = Layout(connect_timeout=30)
        layout.connect_timeout
        # 30
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
    """Write one ``build-tools:`` diagnostic to standard error.

    Parameters
    ----------
    message : str
        Diagnostic text, without the standard prefix.

    Examples
    --------
    ``note("mold available")`` writes ``build-tools: mold available`` to
    standard error.
    """
    print(f"build-tools: {message}", file=sys.stderr)


def is_linux(layout: Layout) -> bool:
    """Return whether the host can use mold, which ships for Linux only.

    Parameters
    ----------
    layout : Layout
        Host details; an empty ``system`` uses ``sys.platform``.

    Returns
    -------
    bool
        ``True`` when the selected system name starts with ``"linux"``.

    Examples
    --------
    ``is_linux(Layout(system="linux"))`` returns ``True``; a Windows layout
    returns ``False``.
    """
    return (layout.system or sys.platform).startswith("linux")


def mold_arch(layout: Layout) -> str:
    """Return the architecture name used by the host's mold tarball.

    Parameters
    ----------
    layout : Layout
        Host details; an empty ``machine`` uses ``platform.machine()``.

    Returns
    -------
    str
        The supported release spelling, either ``"x86_64"`` or
        ``"aarch64"``.

    Raises
    ------
    BuildToolsError
        If the machine has no archive in the pinned mold release.

    Examples
    --------
    ``mold_arch(Layout(machine="arm64"))`` returns ``"aarch64"``.
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
    """Return the mold version reported by the executable on ``PATH``.

    Returns
    -------
    str or None
        The version from a successful, well-formed ``mold --version``
        response; ``None`` when mold is missing, fails, or returns an
        unexpected banner.

    Examples
    --------
    With ``mold 2.41.0`` as the first two banner fields,
    ``installed_mold_version()`` returns ``"2.41.0"``. If ``mold`` is absent
    from ``PATH``, it returns ``None``.
    """
    try:
        result = _run(MOLD, "--version")
    except FileNotFoundError:
        return None
    # `mold --version` prints e.g. "mold 2.41.0 (compatible with GNU ld)".
    fields = (result.stdout or "").split()[:2]
    return fields[1] if result.ok and len(fields) == _MOLD_BANNER_FIELDS else None


def check_mold(layout: Layout) -> list[str]:
    """Return any problems with the linker prerequisite.

    Parameters
    ----------
    layout : Layout
        Pin-file and host configuration used for the check.

    Returns
    -------
    list[str]
        Empty when the pinned mold is available or the host is not Linux;
        otherwise, actionable diagnostics for a missing or mismatched
        version.

    Examples
    --------
    With ``layout = Layout(system="linux")`` and the pinned mold on ``PATH``,
    ``check_mold(layout)`` returns ``[]``. On macOS it reports that mold is
    Linux-only and also returns ``[]``.
    """
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
    """Return any problems with the pinned Rust toolchain prerequisite.

    Parameters
    ----------
    layout : Layout
        Toolchain manifest and host configuration used for the check.

    Returns
    -------
    list[str]
        Empty when the pinned channel and all listed components are installed;
        otherwise, actionable diagnostics for missing prerequisites.

    Examples
    --------
    With ``layout = Layout()`` reading a manifest that pins
    ``nightly-2026-10-18``, and rustup listing that channel with every required
    component, ``check_toolchain(layout)`` returns ``[]``. If
    ``rust-analyzer`` is absent, its diagnostic names it.
    """
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
