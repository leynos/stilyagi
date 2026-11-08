"""Track configuration values through their ordered source layers.

This module is the shared implementation for raw-table merges and the
inspection command's source ledger. It deliberately knows nothing about CLI
argument parsing or filesystem discovery; callers provide those boundaries.
"""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

from .tables import merge_config_tables

type _ConfigSourceKind = typ.Literal["default", "file", "inline", "flag"]


@dc.dataclass(frozen=True, slots=True)
class _ConfigOrigin:
    """Identify the layer that supplied one effective config value."""

    kind: _ConfigSourceKind
    source_file: pathlib.Path | None
    cli_overridden: bool


type _OriginPath = tuple[str, ...]


@dc.dataclass(frozen=True, slots=True)
class _ConfigTableWithOrigins:
    """Pair one raw configuration table with its per-leaf origins.

    Origins are keyed by the tuple of key components rather than by a dotted
    string. A single TOML key may itself contain dots — a `[lint.per-file-ignores]`
    entry named `"*.md"` is the common case — and joining then splitting on `.`
    would silently reinterpret that name as a nested table.
    """

    values: dict[str, object]
    origins: dict[_OriginPath, _ConfigOrigin]


@dc.dataclass(slots=True)
class _OriginMergeState:
    """Carry the origin maps shared by one recursive merge."""

    merged: dict[_OriginPath, _ConfigOrigin]
    override: cabc.Mapping[_OriginPath, _ConfigOrigin]


def _origin_paths(
    table: cabc.Mapping[str, object],
    *,
    origin_for_path: cabc.Callable[[_OriginPath], _ConfigOrigin],
    prefix: _OriginPath = (),
) -> dict[_OriginPath, _ConfigOrigin]:
    """Mark leaves and empty mappings in a nested configuration table."""
    origins: dict[_OriginPath, _ConfigOrigin] = {}
    for key, value in table.items():
        path = (*prefix, key)
        if isinstance(value, cabc.Mapping) and value:
            origins.update(
                _origin_paths(
                    typ.cast("cabc.Mapping[str, object]", value),
                    origin_for_path=origin_for_path,
                    prefix=path,
                )
            )
        else:
            origins[path] = origin_for_path(path)
    return origins


def _config_table_from_layer(
    table: cabc.Mapping[str, object],
    origin: _ConfigOrigin,
) -> _ConfigTableWithOrigins:
    """Attach one source origin to each leaf or empty container."""
    return _ConfigTableWithOrigins(
        values=dict(table),
        origins=_origin_paths(table, origin_for_path=lambda _path: origin),
    )


def _merge_config_tables_with_origins(
    base: _ConfigTableWithOrigins,
    override: _ConfigTableWithOrigins,
) -> _ConfigTableWithOrigins:
    """Merge two tables while following the winning origin at each leaf."""
    merged_origins = dict(base.origins)
    _merge_origin_layers(
        base.values,
        override.values,
        _OriginMergeState(merged_origins, override.origins),
    )
    return _ConfigTableWithOrigins(
        values=merge_config_tables(base.values, override.values),
        origins=merged_origins,
    )


def _merge_origin_layers(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
    state: _OriginMergeState,
    *,
    prefix: _OriginPath = (),
) -> None:
    """Update origins using the same recursive shape as table merging."""
    for key, override_value in override.items():
        path = (*prefix, key)
        _merge_origin_entry(base.get(key), override_value, state, path)


def _merge_origin_entry(
    base_value: object,
    override_value: object,
    state: _OriginMergeState,
    path: _OriginPath,
) -> None:
    """Merge one origin subtree using the matching table operation."""
    if isinstance(base_value, cabc.Mapping) and isinstance(
        override_value, cabc.Mapping
    ):
        base_table = typ.cast("cabc.Mapping[str, object]", base_value)
        override_table = typ.cast("cabc.Mapping[str, object]", override_value)
        _merge_origin_layers(base_table, override_table, state, prefix=path)
        _reconcile_mapping_origin(path, base_table, override_table, state)
        return
    _replace_origin_subtree(path, state)


def _reconcile_mapping_origin(
    path: _OriginPath,
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
    state: _OriginMergeState,
) -> None:
    """Keep only an origin for an empty mapping after recursive merging."""
    if merge_config_tables(base, override):
        state.merged.pop(path, None)
        return
    if base or override:
        return
    origin = state.override.get(path)
    if origin is None:
        return
    state.merged[path] = origin


def _is_within(path: _OriginPath, ancestor: _OriginPath) -> bool:
    """Report whether `path` is `ancestor` itself or lies beneath it."""
    return path[: len(ancestor)] == ancestor


def _replace_origin_subtree(
    path: _OriginPath,
    state: _OriginMergeState,
) -> None:
    """Replace displaced leaf origins with the overriding subtree."""
    _discard_origin_subtree(state.merged, path)
    state.merged.update(
        (origin_path, origin)
        for origin_path, origin in state.override.items()
        if _is_within(origin_path, path)
    )


def _discard_origin_subtree(
    origins: dict[_OriginPath, _ConfigOrigin],
    path: _OriginPath,
) -> None:
    """Remove origins replaced by a scalar or a differently shaped table."""
    for existing_path in tuple(origins):
        if _is_within(existing_path, path):
            del origins[existing_path]


def _apply_cli_layer(
    base: _ConfigTableWithOrigins,
    table: cabc.Mapping[str, object],
    *,
    kind: typ.Literal["inline", "flag"],
) -> _ConfigTableWithOrigins:
    """Apply inline TOML or flags while retaining displaced file origins."""
    layer_origins = _origin_paths(
        table,
        origin_for_path=lambda path: _cli_origin(base.origins, path, kind),
    )
    return _merge_config_tables_with_origins(
        base,
        _ConfigTableWithOrigins(values=dict(table), origins=layer_origins),
    )


def _cli_origin(
    origins: cabc.Mapping[_OriginPath, _ConfigOrigin],
    path: _OriginPath,
    kind: typ.Literal["inline", "flag"],
) -> _ConfigOrigin:
    """Keep any file origin that the CLI value replaces."""
    previous = origins.get(path)
    return _ConfigOrigin(
        kind=kind,
        source_file=previous.source_file if previous is not None else None,
        cli_overridden=True,
    )
