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
    import pathlib

# `rustup component list --installed` prints `<name>-<host triple>`.
_ARCHITECTURES = r"(?:x86_64|aarch64|i686|armv7|riscv64gc|powerpc64le|s390x)"
_DIGEST_ROW_FIELDS = 2


class BuildToolsError(Exception):
    """A prerequisite is missing, mismatched or unverifiable."""


@dc.dataclass(frozen=True, slots=True)
class ToolchainPin:
    """The pinned channel and the components it must carry."""

    channel: str
    components: tuple[str, ...]


def read_pin(path: pathlib.Path) -> str:
    """Return a single-line version pin, trimmed of surrounding whitespace.

    A missing, blank, multi-line or internally spaced pin is refused rather
    than repaired: deleting whitespace would turn ``1.2 3`` into ``1.23`` and
    build a nonsensical download URL.

    Returns
    -------
    str
        The pin, without surrounding whitespace.

    Raises
    ------
    BuildToolsError
        If the pin is absent or malformed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        message = f"missing version pin: {path}"
        raise BuildToolsError(message) from None
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


def read_toolchain(path: pathlib.Path) -> ToolchainPin:
    """Return the channel and components `rust-toolchain.toml` pins.

    Returns
    -------
    ToolchainPin
        The pinned channel and the components it must carry.

    Raises
    ------
    BuildToolsError
        If the file is absent, is not TOML, or names no channel.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError:
        message = f"missing or unreadable toolchain pin: {path}"
        raise BuildToolsError(message) from None
    table = document.get("toolchain", {})
    channel = table.get("channel") if isinstance(table, dict) else None
    if not isinstance(channel, str) or not channel:
        message = f"no channel found in: {path}"
        raise BuildToolsError(message)
    components = tuple(str(name) for name in table.get("components", ()))
    return ToolchainPin(channel=channel, components=components)


def component_present(name: str, installed: list[str]) -> bool:
    """Return whether a `rust-toolchain.toml` component is in rustup's list.

    The manifest spells some components with a ``-preview`` suffix that
    rustup's installed list drops, and appends the host triple to all of them.

    Returns
    -------
    bool
        True when an installed entry is `name` for some host triple.
    """
    base = name.removesuffix("-preview")
    pattern = re.compile(rf"^{re.escape(base)}-{_ARCHITECTURES}-")
    return any(pattern.match(entry) for entry in installed)


def expected_checksum(sums_file: pathlib.Path, name: str) -> str:
    """Return the one digest recorded for `name`.

    Exactly one row must match. An unlisted artefact is a hard failure, and so
    are several rows: a file recording a wrong digest beside the right one must
    not verify because one of them happened to win.

    Returns
    -------
    str
        The recorded SHA-256 digest.

    Raises
    ------
    BuildToolsError
        If the checksum file is unreadable, or does not record exactly one row.
    """
    try:
        rows = sums_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        message = f"missing checksum file: {sums_file}"
        raise BuildToolsError(message) from None
    split_rows = (row.split() for row in rows)
    digests = [
        fields[0]
        for fields in split_rows
        if len(fields) == _DIGEST_ROW_FIELDS and fields[1] == name
    ]
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


def verify_archive(archive: pathlib.Path, expected: str) -> None:
    """Refuse an archive whose SHA-256 digest is not `expected`.

    Raises
    ------
    BuildToolsError
        On a mismatch.
    """
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected.lower():
        message = f"checksum mismatch for {archive.name}; refusing to install"
        raise BuildToolsError(message)
