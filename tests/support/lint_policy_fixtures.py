"""The scratch crates the lint-policy behavioural proof compiles.

`tests/test_lint_policy_behaviour.py` proves the declared lint policy is
effective by compiling code that violates it. This module owns the fixtures
that code is written from: the source of each violating binary, the
documentation-clean library the binaries link, and the two libraries that
differ only in whether the rustdoc table denies a broken intra-doc link.

Each manifest copies the workspace's `[lints]` tables, so a fixture compiles
under the same policy the real members inherit. The tables are read through
`tests.support.lint_policy`, which is the single reader for the repository's
configuration; nothing here interprets the policy itself.

Rendering takes the tables as an argument rather than reading them, so it is a
pure function of what it is given. `write_workspace_crates` is the one boundary
that reads: it supplies the repository's tables to the writer, and reads before
writing anything, so a manifest that cannot be read leaves no fixture behind.

The crates are written into a caller-supplied base directory. The caller owns
that directory's lifetime, so a test run can use a unique path and remove it
afterwards without this module knowing where the tree lives.
"""

import dataclasses
import typing as typ

from tests.support.lint_policy import workspace_lints

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

#: Lint namespace to its entries, the shape `workspace_lints` returns.
type Tables = dict[str, dict[str, object]]

CRATE_NAME: typ.Final = "lint-policy-fixtures"
UNDOCUMENTED_NAME: typ.Final = "lint-policy-fixtures-undocumented"
DENIED_NAME: typ.Final = "lint-policy-fixtures-denied"
WARN_NAME: typ.Final = "lint-policy-fixtures-warn"

ENVIRONMENT_SEAM_SOURCE: typ.Final = (
    '/// Entry point.\nfn main() {\n    drop(std::env::var("HOME"));\n}\n'
)
ASSERT_WITHOUT_MESSAGE_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n"
    "    let count = std::env::args().count();\n"
    "    assert!(count > 0);\n}\n"
)
PRIVATE_ITEM_WITHOUT_DOCS_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n    undocumented();\n}\n\nfn undocumented() {}\n"
)
UNSAFE_BLOCK_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n"
    "    let pointer: *const u8 = std::ptr::null();\n"
    "    let _ = unsafe { *pointer };\n}\n"
)

#: One violating binary per Clippy entry, with the diagnostic it must produce.
CLIPPY_FIXTURES: typ.Final[dict[str, tuple[str, str]]] = {
    "environment_seam": (
        ENVIRONMENT_SEAM_SOURCE,
        "clippy::disallowed_methods",
    ),
    "assert_without_message": (
        ASSERT_WITHOUT_MESSAGE_SOURCE,
        "clippy::missing_assert_message",
    ),
    "private_item_without_docs": (
        PRIVATE_ITEM_WITHOUT_DOCS_SOURCE,
        "clippy::missing_docs_in_private_items",
    ),
    "unsafe_block": (UNSAFE_BLOCK_SOURCE, "unsafe_code"),
}

#: The shared library the binaries link. It satisfies every denied entry on
#: purpose, so it cannot mask a binary's own diagnostic.
LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\n/// Documented.\npub const fn documented() {}\n"
)

#: The library in the second crate, which carries the `missing_docs` violation.
UNDOCUMENTED_LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\npub fn undocumented() {}\n"
)

#: The library in the third and fourth crates. It is fully documented, so the
#: broken intra-doc link is the only violation. The third crate carries the
#: full rustdoc table, which denies the link with no flags at all; the fourth
#: omits that entry, so the lint stays at rustdoc's default `warn` and only
#: `-D warnings` can escalate it.
BROKEN_LINK_LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\n/// See [Nothing] for details.\npub fn documented() {}\n"
)

#: A binary whose broken intra-doc link exists only under `--cfg docsrs`.
DOCSRS_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {}\n\n"
    "#[cfg(docsrs)]\n/// See [Nothing] for details.\npub fn documented() {}\n"
)


@dataclasses.dataclass(frozen=True, slots=True)
class ScratchCrates:
    """The four scratch crates, each in a directory of its own."""

    scratch: pathlib.Path
    undocumented: pathlib.Path
    denied: pathlib.Path
    warn: pathlib.Path


@dataclasses.dataclass(frozen=True, slots=True)
class _Library:
    """One library-only crate: its name, its source and its rustdoc omissions."""

    name: str
    source: str
    omit_rustdoc: frozenset[str] = frozenset()


#: The library-only crates, in the order the fixtures describe them.
LIBRARIES: typ.Final = (
    _Library(UNDOCUMENTED_NAME, UNDOCUMENTED_LIBRARY_SOURCE),
    _Library(DENIED_NAME, BROKEN_LINK_LIBRARY_SOURCE),
    _Library(
        WARN_NAME,
        BROKEN_LINK_LIBRARY_SOURCE,
        frozenset({"broken_intra_doc_links"}),
    ),
)


def _render_value(value: object) -> str:
    """Render one lint entry as TOML, in both the string and table forms."""
    match value:
        case str():
            return f'"{value}"'
        case bool():
            return "true" if value else "false"
        case int():
            return str(value)
        case dict():
            pairs = ", ".join(
                f"{key} = {_render_value(item)}" for key, item in value.items()
            )
            return f"{{ {pairs} }}"
        case _:
            message = f"unexpected lint entry {value!r}"
            raise TypeError(message)


def _manifest(
    name: str, tables: Tables, *, omit_rustdoc: frozenset[str] = frozenset()
) -> str:
    """Render a scratch manifest copying the supplied lint tables.

    `tables` is supplied rather than read here, so rendering is a pure
    function of its arguments: a case can inject tables the repository does
    not declare today, and a failed read cannot leave a half-written fixture
    behind.

    `omit_rustdoc` drops named rustdoc entries. A fixture proving `-D
    warnings` bites must omit the entry rather than set it to `warn`: an
    explicit level beats the `warnings` group, so a manifest `warn` survives
    the flag and would make the case pass for the wrong reason.

    Returns
    -------
    str
        The manifest text to write.
    """
    lines = [
        "[package]",
        f'name = "{name}"',
        'version = "0.0.0"',
        'edition = "2024"',
        "publish = false",
        "",
        "# Detach from the repository workspace; the tables are copied below so",
        "# the fixtures compile under the same policy the members inherit.",
        "[workspace]",
        "",
    ]
    for namespace, entries in tables.items():
        rendered = [
            (lint, value)
            for lint, value in entries.items()
            if not (namespace == "rustdoc" and lint in omit_rustdoc)
        ]
        if not rendered:
            continue
        lines.append(f"[lints.{namespace}]")
        lines.extend(f"{lint} = {_render_value(value)}" for lint, value in rendered)
        lines.append("")
    return "\n".join(lines)


def _write_binary(root: pathlib.Path, name: str, source: str) -> None:
    """Write one binary fixture, with the docs the policy requires."""
    path = root / "src" / "bin" / f"{name}.rs"
    path.write_text(f"//! Probe fixture.\n\n{source}", encoding="utf-8")


def _write_library_crate(
    root: pathlib.Path, library: _Library, tables: Tables
) -> pathlib.Path:
    """Write one library-only scratch crate and return its directory."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        _manifest(library.name, tables, omit_rustdoc=library.omit_rustdoc),
        encoding="utf-8",
    )
    (root / "src" / "lib.rs").write_text(library.source, encoding="utf-8")
    return root


def write_scratch_crates(base: pathlib.Path, tables: Tables) -> ScratchCrates:
    """Write the four scratch crates under `base` and return their directories.

    Parameters
    ----------
    base
        Directory the crates are written under. The caller owns its lifetime.
    tables
        The lint tables each manifest copies, from `workspace_lints`.

    Returns
    -------
    ScratchCrates
        The four crate directories.
    """
    scratch = base / CRATE_NAME
    (scratch / "src" / "bin").mkdir(parents=True, exist_ok=True)
    (scratch / "Cargo.toml").write_text(_manifest(CRATE_NAME, tables), encoding="utf-8")
    (scratch / "src" / "lib.rs").write_text(LIBRARY_SOURCE, encoding="utf-8")
    for name, (source, _) in CLIPPY_FIXTURES.items():
        _write_binary(scratch, name, source)
    _write_binary(scratch, "docsrs_link", DOCSRS_SOURCE)
    libraries = {
        library.name: _write_library_crate(base / library.name, library, tables)
        for library in LIBRARIES
    }
    return ScratchCrates(
        scratch=scratch,
        undocumented=libraries[UNDOCUMENTED_NAME],
        denied=libraries[DENIED_NAME],
        warn=libraries[WARN_NAME],
    )


def write_workspace_crates(
    base: pathlib.Path, *, read: cabc.Callable[[], Tables] = workspace_lints
) -> ScratchCrates:
    """Read the workspace lint tables, then write the crates that copy them.

    The read happens before anything is written, so a policy file that cannot
    be read leaves `base` untouched rather than producing fixtures that
    compile under a policy nobody declared.

    Parameters
    ----------
    base
        Directory the crates are written under. The caller owns its lifetime.
    read
        Reader for the workspace tables. The seam exists so a case can prove
        the ordering with a reader that refuses.

    Returns
    -------
    ScratchCrates
        The four crate directories.
    """
    return write_scratch_crates(base, read())
