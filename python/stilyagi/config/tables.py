"""Raw configuration table primitives used by config resolution.

These helpers know nothing about caching or run state: they merge tables,
parse an inline `--config` fragment, split `--config` values into file paths and
fragments, and locate the directory from which nearest-config discovery should
start. :class:`stilyagi.config.resolve.ConfigResolver` composes them, and
keeping them separate lets that resolver stay a description of *when* each
primitive applies.
"""

import collections.abc as cabc
import pathlib
import tomllib
import typing as typ

from .load import discover_same_directory_config
from .schema import InvalidConfigError
from .validate import ensure_extend_value

if typ.TYPE_CHECKING:
    from .load import LoadedConfig


def merge_config_tables(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
) -> dict[str, object]:
    """Merge two raw config tables with recursive mapping semantics."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, cabc.Mapping) and isinstance(value, cabc.Mapping):
            merged[key] = merge_config_tables(
                typ.cast("cabc.Mapping[str, object]", existing),
                typ.cast("cabc.Mapping[str, object]", value),
            )
            continue
        merged[key] = value
    return merged


def normalise_extend_values(
    value: object,
    *,
    path: pathlib.Path,
) -> tuple[str, ...]:
    """Normalise the raw `extend` value to an ordered tuple of strings."""
    if value is None:
        return ()
    validated = ensure_extend_value(value, path=path, key="extend")
    if isinstance(validated, str):
        return (validated,)
    return tuple(validated)


def load_inline_config(
    fragment: str,
    *,
    path: pathlib.Path,
) -> dict[str, object]:
    """Parse an inline `--config` fragment into a raw table."""
    try:
        parsed = tomllib.loads(fragment)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(path, "config", str(exc)) from exc
    parsed_table: dict[str, object] = parsed
    return parsed_table


def resolve_config_reference(
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


def target_directory(target: pathlib.Path) -> pathlib.Path:
    """Return the directory from which config discovery should start."""
    if target.is_dir():
        return target.expanduser().resolve()
    return target.expanduser().parent.resolve()


def search_ancestors_for_config(directory: pathlib.Path) -> LoadedConfig | None:
    """Walk from a directory to the filesystem root looking for config."""
    current = directory
    while True:
        discovered = discover_same_directory_config(current)
        if discovered is not None:
            return discovered
        if current.parent == current:
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


def split_explicit_config(
    explicit_config: cabc.Iterable[str | pathlib.Path] | None,
) -> tuple[list[pathlib.Path], list[str]]:
    """Split `--config` values into file paths and inline fragments."""
    explicit_paths: list[pathlib.Path] = []
    explicit_inline: list[str] = []
    for value in explicit_config or ():
        kind, payload = _classify_explicit_config(value)
        if kind == "path":
            explicit_paths.append(typ.cast("pathlib.Path", payload))
        else:
            explicit_inline.append(typ.cast("str", payload))
    return explicit_paths, explicit_inline
