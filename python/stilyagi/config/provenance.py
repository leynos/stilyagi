"""Track configuration values through their ordered source layers.

This module is the shared implementation for raw-table merges and the
inspection command's source ledger. It deliberately knows nothing about CLI
argument parsing or filesystem discovery; callers provide those boundaries.
"""

import collections.abc as cabc
import dataclasses as dc
import pathlib
import tomllib
import typing as typ

from .schema import InvalidConfigError
from .validate import ensure_extend_value

type _ConfigSourceKind = typ.Literal["default", "file", "inline", "flag"]


def _normalise_extend_values(
    value: object,
    *,
    path: pathlib.Path,
) -> tuple[str, ...]:
    """Normalise a raw `extend` value to ordered string references."""
    validated = (
        () if value is None else ensure_extend_value(value, path=path, key="extend")
    )
    if isinstance(validated, str):
        return (validated,)
    return tuple(validated)


def _load_inline_config(
    fragment: str,
    *,
    path: pathlib.Path,
) -> dict[str, object]:
    """Parse one inline `--config` fragment into a raw table."""
    try:
        parsed = tomllib.loads(fragment)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(path, "config", str(exc)) from exc
    return dict(parsed)


def _resolve_config_reference(
    reference: str,
    *,
    base_directory: pathlib.Path,
    path: pathlib.Path,
) -> pathlib.Path:
    """Resolve one `extend` reference relative to its config file."""
    candidate = pathlib.Path(reference).expanduser()
    if not candidate.is_absolute():
        candidate = base_directory / candidate
    if candidate.is_file():
        return candidate
    raise InvalidConfigError(path, "extend", f"missing config file: {reference}")


def _classify_explicit_config(
    value: str | pathlib.Path,
) -> tuple[str, str | pathlib.Path]:
    """Classify an explicit config value as inline TOML or a file path."""
    if isinstance(value, pathlib.Path):
        return "path", value

    candidate = pathlib.Path(value).expanduser()
    if "=" in value and not candidate.exists():
        return "inline", value
    if candidate.exists():
        return "path", candidate
    raise InvalidConfigError(candidate, "config", "does not exist")


def _split_explicit_config(
    explicit_config: cabc.Iterable[str | pathlib.Path] | None,
) -> tuple[list[pathlib.Path], list[str]]:
    """Group explicit config values by path and inline source."""
    explicit_paths: list[pathlib.Path] = []
    explicit_inline: list[str] = []
    for value in explicit_config or ():
        kind, payload = _classify_explicit_config(value)
        if kind == "path":
            explicit_paths.append(typ.cast("pathlib.Path", payload))
        else:
            explicit_inline.append(typ.cast("str", payload))
    return explicit_paths, explicit_inline


@dc.dataclass(frozen=True, slots=True)
class _ConfigOrigin:
    """Identify the layer that supplied one effective config value."""

    kind: _ConfigSourceKind
    source_file: pathlib.Path | None
    cli_overridden: bool


@dc.dataclass(frozen=True, slots=True)
class _ConfigTableWithOrigins:
    """Pair one raw configuration table with origins keyed by dotted path."""

    values: dict[str, object]
    origins: dict[str, _ConfigOrigin]


@dc.dataclass(slots=True)
class _OriginMergeState:
    """Carry the origin maps shared by one recursive merge."""

    merged: dict[str, _ConfigOrigin]
    override: cabc.Mapping[str, _ConfigOrigin]


def _merge_config_tables(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
) -> dict[str, object]:
    """Merge config tables recursively, replacing non-mapping values."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, cabc.Mapping) and isinstance(value, cabc.Mapping):
            merged[key] = _merge_config_tables(
                typ.cast("cabc.Mapping[str, object]", existing),
                typ.cast("cabc.Mapping[str, object]", value),
            )
            continue
        merged[key] = value
    return merged


def _origin_paths(
    table: cabc.Mapping[str, object],
    *,
    origin_for_path: cabc.Callable[[tuple[str, ...]], _ConfigOrigin],
    prefix: tuple[str, ...] = (),
) -> dict[str, _ConfigOrigin]:
    """Mark leaves and empty mappings in a nested configuration table."""
    origins: dict[str, _ConfigOrigin] = {}
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
            origins[".".join(path)] = origin_for_path(path)
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
        values=_merge_config_tables(base.values, override.values),
        origins=merged_origins,
    )


def _merge_origin_layers(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
    state: _OriginMergeState,
    *,
    prefix: tuple[str, ...] = (),
) -> None:
    """Update origins using the same recursive shape as table merging."""
    for key, override_value in override.items():
        path = (*prefix, key)
        dotted_path = ".".join(path)
        base_value = base.get(key)
        if isinstance(base_value, cabc.Mapping) and isinstance(
            override_value, cabc.Mapping
        ):
            _merge_origin_layers(
                typ.cast("cabc.Mapping[str, object]", base_value),
                typ.cast("cabc.Mapping[str, object]", override_value),
                state,
                prefix=path,
            )
            if _merge_config_tables(base_value, override_value):
                state.merged.pop(dotted_path, None)
            elif not override_value and not base_value:
                origin = state.override.get(dotted_path)
                if origin is not None:
                    state.merged[dotted_path] = origin
            continue

        _discard_origin_subtree(state.merged, dotted_path)
        state.merged.update(
            (origin_path, origin)
            for origin_path, origin in state.override.items()
            if origin_path == dotted_path or origin_path.startswith(f"{dotted_path}.")
        )


def _discard_origin_subtree(
    origins: dict[str, _ConfigOrigin],
    dotted_path: str,
) -> None:
    """Remove origins replaced by a scalar or a differently shaped table."""
    for existing_path in tuple(origins):
        if existing_path == dotted_path or existing_path.startswith(f"{dotted_path}."):
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
    origins: cabc.Mapping[str, _ConfigOrigin],
    path: tuple[str, ...],
    kind: typ.Literal["inline", "flag"],
) -> _ConfigOrigin:
    """Keep any file origin that the CLI value replaces."""
    previous = origins.get(".".join(path))
    return _ConfigOrigin(
        kind=kind,
        source_file=previous.source_file if previous is not None else None,
        cli_overridden=True,
    )
