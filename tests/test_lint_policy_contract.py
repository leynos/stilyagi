"""Contract for the lint policy this repository enforces.

`Cargo.toml` carries the workspace lint tables and `clippy.toml` carries the
environment-method restrictions, but neither had a test that notices when an
entry disappears. Deleting an enabled lint cannot fail a build, so the gates
would stay green while the policy silently weakened. These tests read the
configuration files and fail when an entry this repository relies on is missing
or weakened.

The two mechanisms are separate, and the tests keep them apart. `[lints]
workspace = true` in a member manifest inherits the `[workspace.lints]` tables;
Clippy reads `clippy.toml` from the workspace root and needs no per-member
stanza, so Cargo's lint inheritance does not carry the restrictions.
"""

import pathlib
import typing as typ

import pytest

from tests.support.build_standard import read_toml

REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE_MANIFEST: typ.Final = REPOSITORY_ROOT / "Cargo.toml"
CLIPPY_CONFIG: typ.Final = REPOSITORY_ROOT / "clippy.toml"
MAKEFILE: typ.Final = REPOSITORY_ROOT / "Makefile"

#: Lints this repository enables, by the table that owns them and the level it
#: sets. A missing or weakened entry is a silent loss of enforcement.
ENABLED_LINTS: typ.Final[dict[str, dict[str, str]]] = {
    "clippy": {
        "disallowed_methods": "deny",
        "missing_assert_message": "deny",
        "missing_docs_in_private_items": "deny",
    },
    "rust": {
        "unknown_lints": "deny",
        "renamed_and_removed_lints": "deny",
        "unsafe_code": "forbid",
        "missing_docs": "deny",
    },
    "rustdoc": {
        "missing_crate_level_docs": "deny",
        "broken_intra_doc_links": "deny",
        "private_intra_doc_links": "deny",
        "bare_urls": "deny",
        "invalid_html_tags": "deny",
        "invalid_codeblock_attributes": "deny",
        "unescaped_backticks": "deny",
    },
}

#: The ambient-environment seams Clippy forbids, in configuration order.
ENVIRONMENT_SEAMS: typ.Final[tuple[str, ...]] = (
    "std::env::var",
    "std::env::var_os",
    "std::env::vars",
    "std::env::vars_os",
    "std::env::set_var",
    "std::env::remove_var",
    "std::env::set_current_dir",
)

RUSTDOC_DEFAULT: typ.Final = (
    "RUSTDOC_FLAGS ?= --cfg docsrs -D warnings $(RUSTDOC_FLAGS_EXTRA)"
)


def _lint_table(document: dict[str, object], table: str) -> dict[str, object]:
    """Return one `[workspace.lints.<table>]` mapping."""
    workspace = document.get("workspace")
    assert isinstance(workspace, dict), "Cargo.toml declares no [workspace] table"
    lints = workspace.get("lints")
    assert isinstance(lints, dict), "Cargo.toml declares no [workspace.lints] tables"
    entries = lints.get(table)
    assert isinstance(entries, dict), (
        f"Cargo.toml declares no [workspace.lints.{table}]"
    )
    return entries


def _member_manifests() -> tuple[pathlib.Path, ...]:
    """Return every workspace member manifest."""
    workspace = read_toml(WORKSPACE_MANIFEST)["workspace"]
    assert isinstance(workspace, dict), "Cargo.toml declares no [workspace] table"
    patterns = workspace["members"]
    assert isinstance(patterns, list), "Cargo.toml declares no member list"
    manifests: list[pathlib.Path] = []
    for pattern in patterns:
        assert isinstance(pattern, str), f"member pattern {pattern!r} is not a string"
        matches = sorted(REPOSITORY_ROOT.glob(pattern))
        directories = [path for path in matches if path.is_dir()]
        manifests.extend(path / "Cargo.toml" for path in directories)
    return tuple(manifests)


def _rustdoc_default_lines() -> list[str]:
    """Return the Makefile lines that set the `RUSTDOC_FLAGS` default."""
    text = MAKEFILE.read_text(encoding="utf-8")
    return [
        line.rstrip()
        for line in text.splitlines()
        if line.startswith("RUSTDOC_FLAGS ?=")
    ]


@pytest.mark.parametrize(
    ("table", "lint", "level"),
    [
        pytest.param(table, lint, level, id=f"{table}:{lint}")
        for table, lints in ENABLED_LINTS.items()
        for lint, level in lints.items()
    ],
)
def test_workspace_lint_table_enables_the_baseline(
    table: str, lint: str, level: str
) -> None:
    """Every baseline lint keeps its level in the workspace tables."""
    entries = _lint_table(read_toml(WORKSPACE_MANIFEST), table)
    enabled = entries.get(lint)
    assert enabled == level, (
        f"expected [workspace.lints.{table}] {lint} = {level!r}, found {enabled!r}"
    )


def test_every_workspace_member_inherits_the_lint_tables() -> None:
    """Each member opts into `[workspace.lints]` with `workspace = true`."""
    manifests = _member_manifests()
    assert manifests, "Cargo.toml declares no workspace members"
    without_inheritance = [
        str(manifest.relative_to(REPOSITORY_ROOT))
        for manifest in manifests
        if _inheritance_flag(read_toml(manifest)) is not True
    ]
    assert without_inheritance == [], (
        "members without `[lints] workspace = true`: " + ", ".join(without_inheritance)
    )


def _inheritance_flag(document: dict[str, object]) -> object:
    """Return a member manifest's `lints.workspace` value, if any."""
    lints = document.get("lints")
    return lints.get("workspace") if isinstance(lints, dict) else None


def test_clippy_restricts_every_environment_seam() -> None:
    """`clippy.toml` forbids each ambient-environment seam, with a reason."""
    document = read_toml(CLIPPY_CONFIG)
    restrictions = document.get("disallowed-methods")
    assert isinstance(restrictions, list), "clippy.toml declares disallowed-methods"
    paths = tuple(
        entry["path"]
        for entry in restrictions
        if isinstance(entry, dict) and "path" in entry
    )
    assert paths == ENVIRONMENT_SEAMS, (
        f"expected the environment seams {ENVIRONMENT_SEAMS}, found {paths}"
    )
    without_reason = [
        entry["path"]
        for entry in restrictions
        if isinstance(entry, dict) and not str(entry.get("reason", "")).strip()
    ]
    assert without_reason == [], "restrictions without a reason: " + ", ".join(
        without_reason
    )


def test_rustdoc_default_enforces_docsrs_and_warnings() -> None:
    """The rustdoc default enables the docsrs cfg and denies warnings."""
    lines = _rustdoc_default_lines()
    assert lines == [RUSTDOC_DEFAULT], (
        f"expected the rustdoc default {RUSTDOC_DEFAULT!r}, found {lines}"
    )


def test_rustdoc_default_stays_overrideable_and_extensible() -> None:
    """The rustdoc default is conditional and keeps the extension seam last."""
    (line,) = _rustdoc_default_lines()
    variable, _, value = line.partition("=")
    assert variable.endswith("?"), (
        "the default must be `?=` so an environment override wins"
    )
    assert value.split()[-1] == "$(RUSTDOC_FLAGS_EXTRA)", (
        "RUSTDOC_FLAGS_EXTRA must stay last so additions append to the policy"
    )
