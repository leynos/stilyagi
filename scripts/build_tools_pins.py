"""Pin readers and verifiers for `build_tools.py`.

Pure functions over the committed pin files, the checksum list and
`rustup`'s component names. Nothing here runs a program, so each reader is
exercised directly and the CLI in `build_tools.py` stays about its tools.
"""

import dataclasses as dc
import hashlib
import re
import tomllib
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

# `rustup component list --installed` prints `<name>-<host triple>`.
_ARCHITECTURES = r"(?:x86_64|aarch64|i686|armv7|riscv64gc|powerpc64le|s390x)"
_DIGEST_ROW_FIELDS = 2


class BuildToolsError(Exception):
    """A prerequisite is missing, mismatched or cannot be verified.

    This exception represents an actionable build-tool configuration or
    verification failure for callers of the pin-reading functions.

    Examples
    --------
    ``read_pin(path)`` raises this exception when the pin file is empty.
    """


@dc.dataclass(frozen=True, slots=True)
class ToolchainPin:
    """The nightly channel and components required by the build standard.

    Attributes
    ----------
    channel : str
        Rustup toolchain channel from ``rust-toolchain.toml``.
    components : tuple[str, ...]
        Components that must be installed for that channel.

    Examples
    --------
    ``ToolchainPin("nightly-2026-10-18", ("rustfmt",))`` represents a dated
    nightly that requires rustfmt.
    """

    channel: str
    components: tuple[str, ...]


def _pin_value(text: str, path: pathlib.Path) -> str:
    """Return the one non-blank, whitespace-free line in `text`."""
    lines = text.splitlines()
    if len(lines) > 1:
        message = f"expected one line in version pin: {path}, found {len(lines)}"
        raise BuildToolsError(message)
    value = text.strip()
    if not value:
        message = f"empty version pin: {path}"
        raise BuildToolsError(message)
    if re.search(r"\s", value):
        message = f"version pin contains whitespace: {path}"
        raise BuildToolsError(message)
    return value


def read_pin(path: pathlib.Path) -> str:
    """Read one version pin and trim surrounding whitespace.

    A missing, blank, multi-line or internally spaced pin is refused rather
    than repaired: deleting whitespace could change the version value.

    Parameters
    ----------
    path : pathlib.Path
        File expected to contain one version on one line.

    Returns
    -------
    str
        The pin without surrounding whitespace.

    Raises
    ------
    BuildToolsError
        If the file is unreadable or the value is empty, multi-line or
        contains whitespace internally.

    Examples
    --------
    If a file contains ``2.41.0`` followed by a newline,
    ``read_pin(path)`` returns ``"2.41.0"``.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        message = f"missing version pin: {path}"
        raise BuildToolsError(message) from None
    return _pin_value(text, path)


def _channel(table: object, path: pathlib.Path) -> str:
    """Return the non-empty channel from a parsed toolchain table."""
    channel = table.get("channel") if isinstance(table, dict) else None
    if not isinstance(channel, str) or not channel:
        message = f"no channel found in: {path}"
        raise BuildToolsError(message)
    return channel


def read_toolchain(path: pathlib.Path) -> ToolchainPin:
    """Read the pinned channel and components from a Rust toolchain manifest.

    Parameters
    ----------
    path : pathlib.Path
        TOML file containing a ``[toolchain]`` table.

    Returns
    -------
    ToolchainPin
        Channel and component names from the manifest.

    Raises
    ------
    BuildToolsError
        If the file is unreadable, invalid TOML or has no non-empty channel.

    Examples
    --------
    Given ``path = pathlib.Path("rust-toolchain.toml")`` containing
    ``channel = "nightly-2026-10-18"`` and ``components = ["rustfmt"]``,
    ``read_toolchain(path)`` returns
    ``ToolchainPin(channel="nightly-2026-10-18", components=("rustfmt",))``.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError:
        message = f"missing or unreadable toolchain pin: {path}"
        raise BuildToolsError(message) from None
    table = document.get("toolchain", {})
    channel = _channel(table, path)
    components = tuple(str(name) for name in table.get("components", ()))
    return ToolchainPin(channel=channel, components=components)


def component_present(name: str, installed: cabc.Iterable[str]) -> bool:
    """Check whether an installed rustup entry matches a manifest component.

    The manifest may add ``-preview`` to a component name; rustup's
    installed list omits it and appends an architecture and host suffix.

    Parameters
    ----------
    name : str
        Component name from the toolchain manifest.
    installed : collections.abc.Iterable[str]
        Installed entries as printed by
        ``rustup component list --installed``.

    Returns
    -------
    bool
        ``True`` when an entry matches the component and a supported host.

    Examples
    --------
    ``component_present("rustfmt", ["rustfmt-x86_64-unknown-linux-gnu"])``
    returns ``True``.
    """
    base = name.removesuffix("-preview")
    pattern = re.compile(rf"^{re.escape(base)}-{_ARCHITECTURES}-")
    return any(pattern.match(entry) for entry in installed)


def _matching_digests(rows: list[str], name: str) -> list[str]:
    """Return the digest column of every two-field row naming `name`."""
    fields = (row.split() for row in rows)
    return [
        parts[0]
        for parts in fields
        if len(parts) == _DIGEST_ROW_FIELDS and parts[1] == name
    ]


def _unique_digest(digests: list[str], name: str, sums_file: pathlib.Path) -> str:
    """Return the one digest for `name`, refusing an absent or repeated row."""
    if not digests:
        message = f"no checksum recorded for {name} in {sums_file}"
        raise BuildToolsError(message)
    if len(digests) > 1:
        message = (
            f"{len(digests)} checksums recorded for {name} in {sums_file}; "
            "refusing to guess"
        )
        raise BuildToolsError(message)
    return digests[0]


def expected_checksum(sums_file: pathlib.Path, name: str) -> str:
    """Read the unique SHA-256 digest recorded for an archive name.

    Exactly one matching row must exist. An absent or duplicated row is
    rejected rather than guessed.

    Parameters
    ----------
    sums_file : pathlib.Path
        Checksum list with digest and archive-name columns.
    name : str
        Exact archive filename to find.

    Returns
    -------
    str
        The recorded SHA-256 digest.

    Raises
    ------
    BuildToolsError
        If the file is unreadable or does not contain exactly one matching
        row.

    Examples
    --------
    If ``sums_file`` contains the row
    ``e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  empty.tar.gz``,
    ``expected_checksum(sums_file, "empty.tar.gz")`` returns that 64-digit
    digest. It is the SHA-256 of an empty file.
    """
    try:
        rows = sums_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        message = f"missing checksum file: {sums_file}"
        raise BuildToolsError(message) from None
    return _unique_digest(_matching_digests(rows, name), name, sums_file)


def verify_archive(archive: pathlib.Path, expected: str) -> None:
    """Refuse an archive whose SHA-256 digest differs from the expected value.

    Parameters
    ----------
    archive : pathlib.Path
        Archive whose bytes are checked.
    expected : str
        Expected hexadecimal SHA-256 digest; letter case is ignored.

    Raises
    ------
    BuildToolsError
        If the calculated digest does not match ``expected``. File-read
        errors from ``pathlib`` are allowed to propagate.

    Examples
    --------
    If ``archive = pathlib.Path("empty.tar.gz")`` names an empty file,
    set ``digest`` to its SHA-256 hexadecimal checksum. The call
    ``verify_archive(archive, digest)`` returns ``None``. A different digest
    raises ``BuildToolsError`` before
    installation.
    """
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected.lower():
        message = f"checksum mismatch for {archive.name}; refusing to install"
        raise BuildToolsError(message)
