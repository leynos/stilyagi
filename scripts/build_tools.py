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

import pathlib
import sys
import tempfile

import cyclopts
from build_tools_environment import (
    CATALOGUE as CATALOGUE,
)
from build_tools_environment import (
    CURL,
    RUSTUP,
    TAR,
    Layout,
    _run,
    check_mold,
    check_toolchain,
    is_linux,
    mold_arch,
    note,
)
from build_tools_environment import (
    MOLD as MOLD,
)
from build_tools_environment import (
    REPOSITORY_ROOT as REPOSITORY_ROOT,
)
from build_tools_environment import (
    installed_mold_version as installed_mold_version,
)
from build_tools_pins import (
    BuildToolsError,
    expected_checksum,
    read_pin,
    read_toolchain,
    verify_archive,
)
from build_tools_pins import (
    component_present as component_present,
)
from cyclopts import App


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

    Parameters
    ----------
    layout : Layout
        Pin files, host overrides and destination prefix for the installation.

    Raises
    ------
    BuildToolsError
        If the download, checksum verification or archive extraction fails.

    Examples
    --------
    For ``layout = Layout(system="linux")``,
    ``install_mold(layout)`` downloads the pinned archive, verifies its
    checksum, and extracts it under ``layout.prefix``. This example describes
    the operation; it does not run the download or installation.
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
    """Install the pinned nightly with the components in its manifest.

    Parameters
    ----------
    layout : Layout
        Path to the toolchain manifest and related installation
        configuration.

    Raises
    ------
    BuildToolsError
        If rustup is missing or cannot install the pinned channel and
        components.

    Examples
    --------
    With ``layout.toolchain_file`` naming a manifest containing
    ``nightly-2026-10-18`` and ``clippy``, the reference call
    ``install_toolchain(layout)`` asks rustup to install that channel and
    component. This installation example is not executed as a doctest.
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
    """Install the pinned mold release and nightly toolchain.

    Parameters
    ----------
    layout : Layout or None, optional
        Installation configuration. ``None`` uses ``Layout()``.

    Notes
    -----
    Installation errors propagate as ``BuildToolsError`` when either
    prerequisite cannot be installed or verified.

    Examples
    --------
    Running ``python scripts/build_tools.py install`` installs the pinned mold
    and toolchain, then prints a message directing the caller to
    ``make check-build-tools``. This command is shown for reference and is not
    run by this example.
    """
    layout = layout or Layout()
    # The linker first, so a checksum failure aborts before a toolchain download.
    install_mold(layout)
    install_toolchain(layout)
    note("ready; verify with: make check-build-tools")


@app.command
def check(layout: Layout | None = None) -> None:
    """Check the prerequisites and exit with failure status if either is absent.

    Parameters
    ----------
    layout : Layout or None, optional
        Check configuration. ``None`` uses ``Layout()``.

    Notes
    -----
    The process exits with status 1 when mold or the pinned toolchain is
    unavailable.

    Examples
    --------
    Running ``python scripts/build_tools.py check`` with both pins installed
    prints success diagnostics and returns normally. If mold is missing, it
    prints an installation hint and exits with status 1.
    """
    layout = layout or Layout()
    # Both halves always run, so one pass reports every missing piece.
    problems = [*check_mold(layout), *check_toolchain(layout)]
    for problem in problems:
        note(problem)
    if problems:
        note("capability check failed; see the messages above")
        sys.exit(1)


def main() -> None:
    """Run the command-line interface and report build-tool failures clearly.

    The CLI maps ``BuildToolsError`` to one ``build-tools:`` diagnostic and exit
    status 1. Other programming errors are not converted.

    Notes
    -----
    The process exits with status 1 for a reported ``BuildToolsError``.

    Examples
    --------
    Running ``python scripts/build_tools.py install`` when rustup is missing
    emits a diagnostic beginning ``build-tools: rustup not found on PATH``,
    followed by the ``install it from https://rustup.rs`` hint, and exits with
    status 1. This reference command is not executed as a doctest.
    """
    try:
        app()
    except BuildToolsError as error:
        note(str(error))
        sys.exit(1)


if __name__ == "__main__":
    main()
