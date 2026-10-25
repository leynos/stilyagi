"""Property checks for inherited configuration provenance."""

import contextlib
import copy
import dataclasses as dc
import io
import json
import pathlib
import tempfile
import typing as typ

from hypothesis import given
from hypothesis import strategies as st
from stilyagi import cli

_DEFAULTS: dict[str, object] = {
    "cache-dir": ".stilyagi_cache",
    "respect-gitignore": True,
    "line-length": 88,
    "plugins": ["builtin"],
    "lint": {
        "select": ["MD", "DOC", "PUN", "STY", "PYDOC"],
        "ignore": [],
        "preview": False,
        "fixable": ["ALL"],
        "unfixable": [],
        "per-file-ignores": {},
    },
    "extract": {"markdown": {"gfm": True, "frontmatter": True, "mdx": False}},
    "nlp": {"model": "en_core_web_sm", "sentence-provider": "sentencizer"},
    "rule": {},
}


def _layer() -> st.SearchStrategy[dict[str, object]]:
    """Generate one sparse config layer with nested and empty values."""
    return st.fixed_dictionaries(
        {},
        optional={
            "cache-dir": st.sampled_from([".cache-a", ".cache-b", "cache-c"]),
            "line-length": st.integers(min_value=60, max_value=120),
            "plugins": st.lists(
                st.sampled_from(["builtin", "custom"]), min_size=0, max_size=3
            ),
            "lint.select": st.lists(
                st.sampled_from(["MD001", "STY001", "DOC001"]),
                min_size=0,
                max_size=3,
            ),
            "lint.preview": st.booleans(),
            "extract.markdown.gfm": st.booleans(),
            "rule": st.one_of(
                st.just({}),
                st.fixed_dictionaries({"enabled": st.booleans()}),
            ),
        },
    )


@st.composite
def _generated_chain(draw: st.DrawFn) -> list[dict[str, object]]:
    """Generate a chain with an inherited value and a later override."""
    base_select = draw(
        st.lists(st.sampled_from(["MD001", "STY001", "DOC001"]), max_size=3)
    )
    final_select = draw(
        st.lists(st.sampled_from(["MD001", "STY001", "DOC001"]), max_size=3)
    )
    intervening = draw(st.lists(_layer(), max_size=2))
    final_layer: dict[str, object] = {
        "lint.select": final_select,
        "extract.markdown.gfm": draw(st.booleans()),
        "rule": draw(
            st.one_of(st.just({}), st.fixed_dictionaries({"enabled": st.booleans()}))
        ),
    }
    return [{"lint.select": base_select}, *intervening, final_layer]


def _toml_value(value: object) -> str:
    """Render the generated scalar or sequence as TOML syntax."""
    return json.dumps(value)


def _write_layer(
    path: pathlib.Path,
    layer: dict[str, object],
    *,
    parent: pathlib.Path | None,
) -> None:
    """Write one generated layer using only the supported TOML shapes."""
    lines: list[str] = []
    if parent is not None:
        lines.append(f"extend = {_toml_value(str(parent))}")
    _append_scalar_values(lines, layer)
    _append_lint_values(lines, layer)
    _append_markdown_values(lines, layer)
    _append_rule_values(lines, layer)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _append_scalar_values(lines: list[str], layer: dict[str, object]) -> None:
    """Append the supported root-level generated TOML values."""
    lines.extend(
        f"{key} = {_toml_value(layer[key])}"
        for key in ("cache-dir", "line-length", "plugins")
        if key in layer
    )


def _append_lint_values(lines: list[str], layer: dict[str, object]) -> None:
    """Append generated lint settings under their TOML table."""
    lint_values = {
        "select": layer.get("lint.select"),
        "preview": layer.get("lint.preview"),
    }
    lint_values = {
        key: value for key, value in lint_values.items() if value is not None
    }
    if lint_values:
        lines.extend(("", "[lint]"))
        lines.extend(
            f"{key} = {_toml_value(value)}" for key, value in lint_values.items()
        )


def _append_markdown_values(lines: list[str], layer: dict[str, object]) -> None:
    """Append generated Markdown extraction settings."""
    if "extract.markdown.gfm" in layer:
        lines.extend((
            "",
            "[extract.markdown]",
            f"gfm = {_toml_value(layer['extract.markdown.gfm'])}",
        ))


def _append_rule_values(lines: list[str], layer: dict[str, object]) -> None:
    """Append generated STY001 rule settings."""
    if "rule" in layer:
        lines.extend(("", "[rule.STY001]"))
        rule_values = typ.cast("dict[str, object]", layer["rule"])
        lines.extend(
            f"{key} = {_toml_value(value)}" for key, value in rule_values.items()
        )


def _flatten_origins(
    value: object,
    *,
    prefix: tuple[str, ...] = (),
    kind: str,
    source_file: str | None,
) -> dict[str, dict[str, object]]:
    """Give each leaf, or empty mapping, one source in the oracle result."""
    if isinstance(value, dict) and value:
        flattened: dict[str, dict[str, object]] = {}
        for key, child in value.items():
            flattened.update(
                _flatten_origins(
                    child,
                    prefix=(*prefix, key),
                    kind=kind,
                    source_file=source_file,
                )
            )
        return flattened

    dotted_key = ".".join(prefix)
    return {
        dotted_key: {
            "kind": kind,
            "source_file": source_file,
            "cli_overridden": kind in {"inline", "flag"},
        }
    }


@dc.dataclass(slots=True)
class _OracleState:
    """Hold effective values and origins for the independent test oracle."""

    values: dict[str, object]
    origins: dict[str, dict[str, object]]


@dc.dataclass(frozen=True, slots=True)
class _OracleLayerMerge:
    """Carry one source identity through an independent layer fold."""

    state: _OracleState
    source_file: pathlib.Path


def _merge_layer(
    state: _OracleState,
    layer: dict[str, object],
    *,
    source_file: pathlib.Path,
) -> None:
    """Fold one nested mapping into the independent value/origin oracle."""
    merge = _OracleLayerMerge(state, source_file)
    _merge_nested_layer(merge, state.values, layer, ())


def _merge_nested_layer(
    merge: _OracleLayerMerge,
    current_values: dict[str, object],
    current_layer: dict[str, object],
    prefix: tuple[str, ...],
) -> None:
    """Fold one table level into the independent value/origin oracle."""
    for key, value in current_layer.items():
        path = (*prefix, key)
        current = current_values.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            current_table = typ.cast("dict[str, object]", current)
            override_table = typ.cast("dict[str, object]", value)
            _merge_nested_layer(
                merge,
                current_table,
                override_table,
                path,
            )
            _reconcile_empty_table_origin(
                merge,
                ".".join(path),
                current_table,
                override_table,
            )
            continue
        _replace_oracle_value(
            merge,
            current_values,
            value,
            path,
        )


def _reconcile_empty_table_origin(
    merge: _OracleLayerMerge,
    dotted_key: str,
    current_table: dict[str, object],
    override_table: dict[str, object],
) -> None:
    """Assign an origin to an empty table or remove its shadowed marker."""
    if current_table:
        merge.state.origins.pop(dotted_key, None)
        return
    if not override_table:
        merge.state.origins[dotted_key] = {
            "kind": "file",
            "source_file": str(merge.source_file.resolve()),
            "cli_overridden": False,
        }


def _replace_oracle_value(
    merge: _OracleLayerMerge,
    current_values: dict[str, object],
    value: object,
    path: tuple[str, ...],
) -> None:
    """Replace one oracle value and every origin below its dotted path."""
    dotted_key = ".".join(path)
    for existing_key in tuple(merge.state.origins):
        if existing_key == dotted_key or existing_key.startswith(f"{dotted_key}."):
            del merge.state.origins[existing_key]
    current_values[path[-1]] = copy.deepcopy(value)
    merge.state.origins.update(
        _flatten_origins(
            value,
            prefix=path,
            kind="file",
            source_file=str(merge.source_file.resolve()),
        )
    )


def _render_expected(
    layers: list[tuple[pathlib.Path, dict[str, object]]],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Apply generated file layers over independent schema defaults."""
    state = _OracleState(
        values=copy.deepcopy(_DEFAULTS),
        origins=_flatten_origins(_DEFAULTS, kind="default", source_file=None),
    )
    for index, (path, layer) in enumerate(layers):
        effective_layer = _nested_layer(layer)
        if index > 0:
            effective_layer["extend"] = str(layers[index - 1][0])
        _merge_layer(state, effective_layer, source_file=path)
    return state.values, state.origins


def _nested_layer(layer: dict[str, object]) -> dict[str, object]:
    """Expand generated dotted keys into their independent TOML tables."""
    nested: dict[str, object] = {}
    for key, value in layer.items():
        match key:
            case "lint.select" | "lint.preview" as lint_key:
                leaf = lint_key.removeprefix("lint.")
                typ.cast("dict[str, object]", nested.setdefault("lint", {}))[leaf] = (
                    value
                )
            case "extract.markdown.gfm":
                markdown = typ.cast(
                    "dict[str, object]",
                    typ.cast(
                        "dict[str, object]", nested.setdefault("extract", {})
                    ).setdefault("markdown", {}),
                )
                markdown["gfm"] = value
            case "rule":
                nested["rule"] = {"STY001": value}
            case _:
                nested[key] = value
    return nested


def _write_generated_chain(
    tmp_path: pathlib.Path,
    layers: list[dict[str, object]],
) -> tuple[list[tuple[pathlib.Path, dict[str, object]]], pathlib.Path, pathlib.Path]:
    """Write a generated chain and its inspection target."""
    written_layers: list[tuple[pathlib.Path, dict[str, object]]] = []
    parent: pathlib.Path | None = None
    for index, layer in enumerate(layers):
        path = tmp_path / f"layer-{index}.toml"
        _write_layer(path, layer, parent=parent)
        written_layers.append((path, layer))
        parent = path

    target = tmp_path / "target.md"
    target.write_text("# target\n", encoding="utf-8")
    assert parent is not None, "expected at least the generated base config"
    return written_layers, parent, target


def _inspect_generated_chain(
    target: pathlib.Path,
    config_file: pathlib.Path,
) -> tuple[int, str, dict[str, object]]:
    """Run config inspection and return its status, error, and JSON result."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = cli.main([
            "config",
            "--target",
            str(target),
            "--isolated",
            "--config",
            str(config_file),
            "--output-format",
            "json",
        ])
    return exit_code, stderr.getvalue(), json.loads(stdout.getvalue())


@given(_generated_chain())
def test_generated_extend_chains_match_independent_layer_fold(
    layers: list[dict[str, object]],
) -> None:
    """Match effective values and origins across generated acyclic chains."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        tmp_path = pathlib.Path(temporary_directory)
        written_layers, parent, target = _write_generated_chain(tmp_path, layers)
        exit_code, error, payload = _inspect_generated_chain(target, parent)
        expected_values, expected_origins = _render_expected(written_layers)

        assert exit_code == 0, f"expected generated config to resolve: {error}"
        assert payload["values"] == expected_values, (
            "expected generated layer values to match the independent fold"
        )
        assert payload["origins"] == expected_origins, (
            "expected generated source origins to match the independent fold"
        )
