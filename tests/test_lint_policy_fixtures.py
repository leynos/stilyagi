"""The rendering rules the scratch-crate fixtures depend on.

`tests/support/lint_policy_fixtures.py` renders the `[lints]` tables that the
behavioural proof compiles under. The behavioural proof only observes the
tables the workspace declares today, so the renderer's other paths — value
forms the present tables do not use, and a namespace whose every entry is
omitted — would otherwise go unexercised. A renderer that guessed at an
unknown value, or that emitted an empty `[lints.<namespace>]` table, would
change what the behavioural proof measures without changing what it asserts.

The cases here inject their own tables, so each one pins the renderer rather
than the repository's current policy; the behavioural proof separately asserts
that the written manifests carry the real tables. The last case pins the
boundary's ordering: the workspace tables are read before anything is written.

These cases write nothing to disk except the base directory the ordering case
proves is left untouched.
"""

import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.lint_policy_fixtures import (
    Tables,
    _manifest,
    _render_value,
    write_workspace_crates,
)

if typ.TYPE_CHECKING:
    import pathlib

#: Tables the renderer cases inject, covering both entry forms and a namespace
#: whose only entry is omitted.
INJECTED_TABLES: typ.Final[Tables] = {
    "clippy": {
        "pedantic": {"level": "warn", "priority": -1},
        "unwrap_used": "deny",
    },
    "rustdoc": {"broken_intra_doc_links": "deny"},
}


@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        pytest.param("deny", '"deny"', id="string"),
        pytest.param(True, "true", id="true"),
        pytest.param(False, "false", id="false"),
        pytest.param(3, "3", id="integer"),
        pytest.param(
            {"level": "warn", "priority": 2},
            '{ level = "warn", priority = 2 }',
            id="table",
        ),
    ],
)
def test_the_renderer_writes_every_toml_value_form(
    value: object, rendered: str
) -> None:
    """Each value form the tables allow renders as the TOML it denotes."""
    assert _render_value(value) == rendered, (
        f"expected {value!r} to render as {rendered}, got {_render_value(value)!r}"
    )


def test_the_renderer_refuses_an_unknown_value() -> None:
    """A value with no TOML rendering is refused rather than guessed at."""
    with pytest.raises(TypeError, match="unexpected lint entry"):
        _render_value(1.5)


def test_an_omitted_namespace_leaves_no_empty_table() -> None:
    """Omitting every entry of a namespace drops the table entirely."""
    rustdoc = frozenset(INJECTED_TABLES["rustdoc"])
    manifest = _manifest("probe", INJECTED_TABLES, omit_rustdoc=rustdoc)
    assert "[lints.rustdoc]" not in manifest, (
        "an omitted namespace must not leave an empty table behind"
    )
    assert any(
        f"[lints.{namespace}]" in manifest
        for namespace in INJECTED_TABLES
        if namespace != "rustdoc"
    ), "the other namespaces must still render"


def test_the_manifest_copies_every_supplied_entry() -> None:
    """Every entry of every supplied namespace reaches the rendered manifest."""
    manifest = _manifest("probe", INJECTED_TABLES)
    for namespace, entries in INJECTED_TABLES.items():
        assert f"[lints.{namespace}]" in manifest, (
            f"expected a [lints.{namespace}] table in {manifest!r}"
        )
        missing = [lint for lint in entries if f"{lint} = " not in manifest]
        assert missing == [], f"expected every {namespace} entry, missing {missing}"


def test_the_manifest_omits_a_namespace_the_tables_do_not_declare() -> None:
    """A namespace absent from the supplied tables is never invented."""
    manifest = _manifest("probe", {"clippy": {"unwrap_used": "deny"}})
    assert "[lints.rustdoc]" not in manifest, (
        "the renderer must not add a table the caller did not supply"
    )


def test_a_failed_policy_read_writes_no_fixture(tmp_path: pathlib.Path) -> None:
    """A reader that refuses leaves the base directory untouched."""
    base = tmp_path / "crates"

    def refuse() -> dict[str, dict[str, object]]:
        """Stand in for a workspace manifest that cannot be read."""
        raise ReadingError("probe", reader="lint_policy", path="Cargo.toml")

    with pytest.raises(ReadingError):
        write_workspace_crates(base, read=refuse)
    assert not base.exists(), "a failed read must not leave a fixture behind"
