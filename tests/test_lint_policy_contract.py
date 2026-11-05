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

These tests read the policy; `tests/test_lint_policy_behaviour.py` compiles
against it.
"""

import typing as typ

import pytest

from tests.support.build_standard import read_toml
from tests.support.lint_policy import (
    RUSTDOC_FLAGS_EXTRA,
    clippy_restrictions,
    lint_level,
    member_manifests,
    rustdoc_default_lines,
    workspace_lints,
)

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
    f"RUSTDOC_FLAGS ?= --cfg docsrs -D warnings {RUSTDOC_FLAGS_EXTRA}"
)


def _inheritance_flag(document: dict[str, object]) -> object:
    """Return a member manifest's `lints.workspace` value, if any."""
    lints = document.get("lints")
    return lints.get("workspace") if isinstance(lints, dict) else None


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
    entries = workspace_lints()[table]
    entry = entries.get(lint)
    enabled = None if entry is None else lint_level(entry)
    assert enabled == level, (
        f"expected [workspace.lints.{table}] {lint} = {level!r}, found {enabled!r}"
    )


def test_every_workspace_member_inherits_the_lint_tables() -> None:
    """Each member opts into `[workspace.lints]` with `workspace = true`."""
    manifests = member_manifests()
    assert manifests, "Cargo.toml declares no workspace members"
    without_inheritance = [
        str(manifest.parent.name)
        for manifest in manifests
        if _inheritance_flag(read_toml(manifest)) is not True
    ]
    assert without_inheritance == [], (
        "members without `[lints] workspace = true`: " + ", ".join(without_inheritance)
    )


def test_clippy_restricts_every_environment_seam() -> None:
    """`clippy.toml` forbids each ambient-environment seam, with a reason."""
    restrictions = clippy_restrictions()
    assert restrictions, "clippy.toml declares no disallowed-methods entries"
    paths = tuple(entry.get("path") for entry in restrictions)
    assert paths == ENVIRONMENT_SEAMS, (
        f"expected the environment seams {ENVIRONMENT_SEAMS}, found {paths}"
    )
    without_reason = [
        str(entry["path"])
        for entry in restrictions
        if not str(entry.get("reason", "")).strip()
    ]
    assert without_reason == [], "restrictions without a reason: " + ", ".join(
        without_reason
    )


def test_rustdoc_default_enforces_docsrs_and_warnings() -> None:
    """The rustdoc default enables the docsrs cfg and denies warnings."""
    lines = rustdoc_default_lines()
    assert lines == [RUSTDOC_DEFAULT], (
        f"expected the rustdoc default {RUSTDOC_DEFAULT!r}, found {lines}"
    )


def test_rustdoc_default_stays_overridable_and_extensible() -> None:
    """The rustdoc default is conditional and keeps the extension seam last."""
    (line,) = rustdoc_default_lines()
    variable, _, value = line.partition("=")
    assert variable.endswith("?"), (
        "the default must be `?=` so an environment override wins"
    )
    assert value.split()[-1] == RUSTDOC_FLAGS_EXTRA, (
        "RUSTDOC_FLAGS_EXTRA must stay last so additions append to the policy"
    )
