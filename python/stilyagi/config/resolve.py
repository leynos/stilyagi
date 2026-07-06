"""Configuration resolution helpers for Stilyagi."""

from __future__ import annotations

import collections.abc as cabc
import pathlib
import tomllib
import typing as typ

from .load import (
    _load_config_table,
    _parse_config_table,
    discover_same_directory_config,
)
from .schema import InvalidConfigError, StilyagiConfig

_DISCOVERY_CACHE: dict[pathlib.Path, pathlib.Path | None] = {}
_RESOLVED_TABLE_CACHE: dict[pathlib.Path, dict[str, object]] = {}


def _merge_config_tables(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
) -> dict[str, object]:
    """Merge two raw config tables with recursive mapping semantics."""
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


def _normalise_extend_values(
    value: object,
    *,
    path: pathlib.Path,
) -> tuple[str, ...]:
    """Normalise the raw `extend` value to an ordered tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, cabc.Sequence) or isinstance(value, (bytes, bytearray)):
        raise InvalidConfigError(
            path, "extend", "must be a string or a list of strings"
        )
    items = tuple(value)
    if any(not isinstance(item, str) for item in items):
        raise InvalidConfigError(path, "extend", "must contain strings only")
    return typ.cast("tuple[str, ...]", items)


def _load_inline_config(
    fragment: str,
    *,
    path: pathlib.Path,
) -> dict[str, object]:
    """Parse an inline `--config` fragment into a raw table."""
    try:
        parsed = tomllib.loads(fragment)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(path, "config", str(exc)) from exc
    if not isinstance(parsed, cabc.Mapping):
        raise InvalidConfigError(path, "config", "must be a mapping")
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


def _resolve_config_table(
    path: pathlib.Path,
    *,
    stack: tuple[pathlib.Path, ...] = (),
) -> dict[str, object]:
    """Resolve a config file and its explicit `extend` chain."""
    resolved_path = path.expanduser().resolve()
    if resolved_path in stack:
        cycle = " -> ".join(str(item) for item in (*stack, resolved_path))
        raise InvalidConfigError(path, "extend", f"cycle detected: {cycle}")

    cached = _RESOLVED_TABLE_CACHE.get(resolved_path)
    if cached is not None:
        return cached

    config_table = dict(_load_config_table(resolved_path))
    extend_values = _normalise_extend_values(
        config_table.get("extend"), path=resolved_path
    )

    merged: dict[str, object] = {}
    next_stack = (*stack, resolved_path)
    for extend_value in extend_values:
        parent_path = _resolve_config_reference(
            extend_value,
            base_directory=resolved_path.parent,
            path=resolved_path,
        )
        parent_table = _resolve_config_table(parent_path, stack=next_stack)
        merged = _merge_config_tables(merged, parent_table)

    merged = _merge_config_tables(merged, config_table)
    _RESOLVED_TABLE_CACHE[resolved_path] = merged
    return merged


def _target_directory(target: pathlib.Path) -> pathlib.Path:
    """Return the directory from which config discovery should start."""
    if target.is_dir():
        return target.expanduser().resolve()
    return target.expanduser().parent.resolve()


def _discover_nearest_config(directory: pathlib.Path) -> pathlib.Path | None:
    """Return the nearest supported config file for one directory."""
    cached = _DISCOVERY_CACHE.get(directory)
    if cached is not None or directory in _DISCOVERY_CACHE:
        return cached

    current = directory
    while True:
        discovered = discover_same_directory_config(current)
        if discovered is not None:
            _DISCOVERY_CACHE[directory] = discovered.path
            return discovered.path
        if current.parent == current:
            _DISCOVERY_CACHE[directory] = None
            return None
        current = current.parent


def _classify_explicit_config(
    value: str | pathlib.Path,
) -> tuple[str, str | pathlib.Path]:
    """Classify one `--config` value as inline TOML or a file path."""
    if isinstance(value, pathlib.Path):
        return "path", value

    candidate = pathlib.Path(value).expanduser()
    if "=" in value and not candidate.exists():
        return "inline", value
    if candidate.exists():
        return "path", candidate
    raise InvalidConfigError(candidate, "config", "does not exist")


def resolve_config_for_path(
    target: pathlib.Path,
    *,
    cli_overrides: cabc.Mapping[str, object] | None,
    explicit_config: cabc.Iterable[str | pathlib.Path] | None,
    isolated: bool,
) -> StilyagiConfig:
    """Resolve the effective config for one target path."""
    resolved_table: dict[str, object] = {}

    if not isolated:
        discovered_path = _discover_nearest_config(_target_directory(target))
        if discovered_path is not None:
            resolved_table = _resolve_config_table(discovered_path)

    explicit_paths: list[pathlib.Path] = []
    explicit_inline: list[str] = []
    for value in explicit_config or ():
        kind, payload = _classify_explicit_config(value)
        if kind == "path":
            explicit_paths.append(typ.cast("pathlib.Path", payload))
        else:
            explicit_inline.append(typ.cast("str", payload))

    for config_path in explicit_paths:
        resolved_table = _merge_config_tables(
            resolved_table, _resolve_config_table(config_path)
        )

    for fragment in explicit_inline:
        resolved_table = _merge_config_tables(
            resolved_table, _load_inline_config(fragment, path=target)
        )

    if cli_overrides:
        resolved_table = _merge_config_tables(resolved_table, dict(cli_overrides))

    return _parse_config_table(resolved_table, path=target)
