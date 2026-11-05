"""Readers for the repository's lint policy.

The contract test and the behavioural test must interpret the same
configuration the same way, so the readers live here rather than in either
test module. Every function is a query over `Cargo.toml`, `clippy.toml` or the
`Makefile`; none of them mutate the tree.

All file access goes through `_read_text` and `_read_toml`, which turn an
unreadable, undecodable or malformed file into `ReadingError` with the reader
and path attached. A broken policy therefore fails as a policy finding rather
than as an incidental `OSError` or `tomllib` traceback, and a structural
surprise such as a non-table restriction is rejected instead of being skipped.

The one reader that leaves the filesystem is `member_manifests`, which lives in
`tests.support.cargo_metadata`: it asks Cargo for the resolved member set rather
than expanding the manifest's patterns itself, because a path dependency inside
the workspace directory is a member even when no pattern matches it.
"""

import pathlib
import re
import tomllib
import typing as typ

from tests.support.errors import ReadingError

REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE_MANIFEST: typ.Final = REPOSITORY_ROOT / "Cargo.toml"
CLIPPY_CONFIG: typ.Final = REPOSITORY_ROOT / "clippy.toml"
MAKEFILE: typ.Final = REPOSITORY_ROOT / "Makefile"

#: The Makefile variable the rustdoc default appends last, so callers extend
#: the policy without editing the default itself.
RUSTDOC_FLAGS_EXTRA: typ.Final = "$(RUSTDOC_FLAGS_EXTRA)"

#: Every way Make can assign `RUSTDOC_FLAGS`: conditional, simple, immediate,
#: append and shell. A second assignment using any of them can silently
#: replace or extend the default, so the reader must see all of them.
_RUSTDOC_ASSIGNMENT: typ.Final = re.compile(
    r"^\s*(?:(?:export|override)\s+)*RUSTDOC_FLAGS\s*(\?=|\+=|::=|:=|=|!=)"
)


def _read_text(path: pathlib.Path) -> str:
    """Return a policy file's text, reporting an unreadable file as a finding."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        message = f"cannot read policy file: {error}"
        raise ReadingError(message, reader="lint_policy", path=str(path)) from error


def _read_toml(path: pathlib.Path) -> dict[str, object]:
    """Return a policy file's parsed TOML document."""
    text = _read_text(path)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        message = f"policy file is not valid TOML: {error}"
        raise ReadingError(message, reader="lint_policy", path=str(path)) from error


def workspace_table(path: pathlib.Path) -> dict[str, object]:
    """Return the root manifest's `[workspace]` table.

    Parameters
    ----------
    path
        The workspace manifest to read.

    Returns
    -------
    dict
        The `[workspace]` table, as declared in the root manifest.

    Raises
    ------
    ReadingError
        If the file cannot be read or parsed, or declares no `[workspace]`
        table.
    """
    workspace = _read_toml(path).get("workspace")
    if not isinstance(workspace, dict):
        message = "Cargo.toml declares no [workspace] table"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    return workspace


def workspace_lints(
    path: pathlib.Path = WORKSPACE_MANIFEST,
) -> dict[str, dict[str, object]]:
    """Return the `[workspace.lints]` tables keyed by lint namespace.

    Entries keep their TOML form: most are level strings, but a group such as
    `pedantic` is a table carrying a `level` and a `priority`.

    Parameters
    ----------
    path
        The workspace manifest to read; the default is this repository's.

    Returns
    -------
    dict
        Lint namespace to its entries, as declared in the root manifest.

    Raises
    ------
    ReadingError
        If the file cannot be read or parsed, has no `[workspace.lints]`
        table, or a namespace's entries are not a table.
    """
    lints = workspace_table(path).get("lints")
    if not isinstance(lints, dict):
        message = "Cargo.toml declares no [workspace.lints] tables"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    tables: dict[str, dict[str, object]] = {}
    for namespace, entries in lints.items():
        if not isinstance(entries, dict):
            message = f"[workspace.lints.{namespace}] is not a table"
            raise ReadingError(message, reader="lint_policy", path=str(path))
        tables[namespace] = dict(entries)
    return tables


def lint_level(entry: object) -> str:
    """Return the level a lint entry sets, from either TOML form.

    Parameters
    ----------
    entry
        One value from a `[workspace.lints.<namespace>]` table: either a
        level string, or a table carrying `level` and optional `priority`.

    Returns
    -------
    str
        The level declared by the entry.

    Raises
    ------
    ReadingError
        If the entry is neither form and so declares no level.
    """
    match entry:
        case str():
            return entry
        case {"level": str() as level}:
            return level
        case _:
            message = f"lint entry {entry!r} declares no string level"
            raise ReadingError(
                message, reader="lint_policy", path=str(WORKSPACE_MANIFEST)
            )


def member_inherits_workspace_lints(path: pathlib.Path) -> bool:
    """Return whether a member manifest opts into the workspace lint tables.

    Parameters
    ----------
    path
        The member manifest to read.

    Returns
    -------
    bool
        Whether the manifest declares `lints.workspace = true`.

    Notes
    -----
    An unreadable, undecodable or malformed manifest raises `ReadingError`
    from `_read_toml`; the raise is indirect, so it is described here rather
    than in a `Raises` section that would claim this function raises it
    itself.
    """
    lints = _read_toml(path).get("lints")
    workspace = lints.get("workspace") if isinstance(lints, dict) else None
    return workspace is True


def clippy_restrictions(
    path: pathlib.Path = CLIPPY_CONFIG,
) -> tuple[dict[str, object], ...]:
    """Return the `disallowed-methods` entries declared in `clippy.toml`.

    Parameters
    ----------
    path
        The Clippy configuration to read; the default is this repository's.

    Returns
    -------
    tuple
        One dict per restriction, each naming a `path` and a `reason`.

    Raises
    ------
    ReadingError
        If the file cannot be read or parsed, declares no
        `disallowed-methods` list, or any entry in it is not a table.
    """
    entries = _read_toml(path).get("disallowed-methods")
    if not isinstance(entries, list):
        message = "clippy.toml declares no disallowed-methods list"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    restrictions: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            message = f"disallowed-methods entry {entry!r} is not a table"
            raise ReadingError(message, reader="lint_policy", path=str(path))
        restrictions.append(dict(entry))
    return tuple(restrictions)


def rustdoc_default_lines(path: pathlib.Path = MAKEFILE) -> list[str]:
    """Return every Makefile line that assigns `RUSTDOC_FLAGS`.

    Every assignment operator is matched, with an optional `export` or
    `override` prefix and any surrounding whitespace. A second assignment
    using `=`, `:=` or `+=` would replace or extend the conditional default,
    so the contract test can only pin the default if it sees all of them.

    Parameters
    ----------
    path
        The Makefile to read; the default is this repository's.

    Returns
    -------
    list
        The matching lines, stripped of surrounding whitespace.

    Notes
    -----
    An unreadable or undecodable file raises `ReadingError` from `_read_text`;
    the raise is indirect, so it is described here rather than in a `Raises`
    section that would claim this function raises it itself.
    """
    return [
        line.strip()
        for line in _read_text(path).splitlines()
        if _RUSTDOC_ASSIGNMENT.match(line)
    ]


def rustdoc_default(path: pathlib.Path = MAKEFILE) -> str:
    """Return the one Makefile line that assigns `RUSTDOC_FLAGS`.

    A caller that reads the default needs exactly one assignment: none means
    the route passes no policy, and a second means one assignment silently
    replaces or extends the default the contract pins. Both are policy
    findings, so they are raised here rather than left to a caller's
    unpacking.

    Parameters
    ----------
    path
        The Makefile to read; the default is this repository's.

    Returns
    -------
    str
        The assignment line, stripped of surrounding whitespace.

    Raises
    ------
    ReadingError
        If the file cannot be read or decoded, or the number of assignments
        is not exactly one.
    """
    lines = rustdoc_default_lines(path)
    if len(lines) != 1:
        message = f"expected exactly one RUSTDOC_FLAGS assignment, found {len(lines)}"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    return lines[0]
