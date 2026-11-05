"""Readers for the repository's lint policy.

The contract test and the behavioural test must interpret the same
configuration the same way, so the readers live here rather than in either
test module. Every function is a query over `Cargo.toml`, `clippy.toml` or the
`Makefile`; none of them mutate the tree.
"""

import pathlib
import typing as typ

from tests.support.build_standard import read_toml
from tests.support.errors import ReadingError

REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[2]
WORKSPACE_MANIFEST: typ.Final = REPOSITORY_ROOT / "Cargo.toml"
CLIPPY_CONFIG: typ.Final = REPOSITORY_ROOT / "clippy.toml"
MAKEFILE: typ.Final = REPOSITORY_ROOT / "Makefile"

#: The Makefile variable the rustdoc default appends last, so callers extend
#: the policy without editing the default itself.
RUSTDOC_FLAGS_EXTRA: typ.Final = "$(RUSTDOC_FLAGS_EXTRA)"


def _workspace_table() -> dict[str, object]:
    """Return the root manifest's `[workspace]` table."""
    workspace = read_toml(WORKSPACE_MANIFEST).get("workspace")
    if not isinstance(workspace, dict):
        message = "Cargo.toml declares no [workspace] table"
        raise ReadingError(message, reader="lint_policy", path=str(WORKSPACE_MANIFEST))
    return workspace


def workspace_lints() -> dict[str, dict[str, object]]:
    """Return the `[workspace.lints]` tables keyed by lint namespace.

    Entries keep their TOML form: most are level strings, but a group such as
    `pedantic` is a table carrying a `level` and a `priority`.

    Returns
    -------
    dict
        Lint namespace to its entries, as declared in the root manifest.

    Raises
    ------
    ReadingError
        If the manifest has no `[workspace.lints]` table, or a namespace's
        entries are not a table.
    """
    lints = _workspace_table().get("lints")
    if not isinstance(lints, dict):
        message = "Cargo.toml declares no [workspace.lints] tables"
        raise ReadingError(message, reader="lint_policy", path=str(WORKSPACE_MANIFEST))
    tables: dict[str, dict[str, object]] = {}
    for namespace, entries in lints.items():
        if not isinstance(entries, dict):
            message = f"[workspace.lints.{namespace}] is not a table"
            raise ReadingError(
                message, reader="lint_policy", path=str(WORKSPACE_MANIFEST)
            )
        tables[namespace] = dict(entries)
    return tables


def lint_level(entry: object) -> str:
    """Return the level a lint entry sets, from either TOML form."""
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


def member_manifests() -> tuple[pathlib.Path, ...]:
    """Return every workspace member manifest."""
    patterns = _workspace_table().get("members")
    if not isinstance(patterns, list):
        message = "Cargo.toml declares no member list"
        raise ReadingError(message, reader="lint_policy", path=str(WORKSPACE_MANIFEST))
    manifests: list[pathlib.Path] = []
    for pattern in patterns:
        if not isinstance(pattern, str):
            message = f"member pattern {pattern!r} is not a string"
            raise ReadingError(
                message, reader="lint_policy", path=str(WORKSPACE_MANIFEST)
            )
        manifests.extend(
            path / "Cargo.toml"
            for path in sorted(REPOSITORY_ROOT.glob(pattern))
            if path.is_dir()
        )
    return tuple(manifests)


def clippy_restrictions() -> tuple[dict[str, object], ...]:
    """Return the `disallowed-methods` entries declared in `clippy.toml`."""
    entries = read_toml(CLIPPY_CONFIG).get("disallowed-methods")
    if not isinstance(entries, list):
        message = "clippy.toml declares no disallowed-methods list"
        raise ReadingError(message, reader="lint_policy", path=str(CLIPPY_CONFIG))
    return tuple(entry for entry in entries if isinstance(entry, dict))


def rustdoc_default_lines() -> list[str]:
    """Return the Makefile lines that set the `RUSTDOC_FLAGS` default."""
    text = MAKEFILE.read_text(encoding="utf-8")
    return [
        line.rstrip()
        for line in text.splitlines()
        if line.startswith("RUSTDOC_FLAGS ?=")
    ]
