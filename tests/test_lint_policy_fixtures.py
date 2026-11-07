"""The rendering rules the scratch-crate fixtures depend on.

`tests/support/lint_policy_fixtures.py` renders the `[lints]` tables that the
behavioural proof compiles under. The behavioural proof only observes the
tables the workspace declares today, so the renderer's other paths — value
forms the present tables do not use, and a namespace whose every entry is
omitted — would otherwise go unexercised. A renderer that guessed at an
unknown value, or that emitted an empty `[lints.<namespace>]` table, would
change what the behavioural proof measures without changing what it asserts.

These cases call the renderer directly, and write nothing to disk.
"""

import typing as typ

import pytest

from tests.support.lint_policy import workspace_lints
from tests.support.lint_policy_fixtures import _manifest, _render_value

#: Namespace to its entries, for the assertions that read the real tables.
WORKSPACE_TABLES: typ.Final = workspace_lints()


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
    rustdoc = frozenset(WORKSPACE_TABLES["rustdoc"])
    manifest = _manifest("probe", omit_rustdoc=rustdoc)
    assert "[lints.rustdoc]" not in manifest, (
        "an omitted namespace must not leave an empty table behind"
    )
    assert any(
        f"[lints.{namespace}]" in manifest
        for namespace in WORKSPACE_TABLES
        if namespace != "rustdoc"
    ), "the other namespaces must still render"


def test_the_manifest_copies_every_declared_entry() -> None:
    """Every entry of every namespace reaches the rendered manifest."""
    manifest = _manifest("probe")
    for namespace, entries in WORKSPACE_TABLES.items():
        assert f"[lints.{namespace}]" in manifest, (
            f"expected a [lints.{namespace}] table in {manifest!r}"
        )
        missing = [lint for lint in entries if f"{lint} = " not in manifest]
        assert missing == [], f"expected every {namespace} entry, missing {missing}"
