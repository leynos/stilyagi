"""Configuration resolution helpers for Stilyagi."""

import collections
import collections.abc as cabc
import dataclasses as dc
import logging
import pathlib
import tomllib
import typing as typ

from .load import discover_same_directory_config, load_config_table
from .parse import parse_config_table
from .schema import InvalidConfigError, StilyagiConfig
from .validate import ensure_extend_value

if typ.TYPE_CHECKING:
    from .load import LoadedConfig

_LOGGER = logging.getLogger(__name__)


def _empty_discovery_cache() -> dict[pathlib.Path, pathlib.Path | None]:
    """Create an independently mutable discovery cache."""
    return {}


def _empty_resolved_table_cache() -> dict[pathlib.Path, dict[str, object]]:
    """Create an independently mutable resolved-table cache."""
    return {}


def _empty_raw_table_cache() -> dict[pathlib.Path, cabc.Mapping[str, object]]:
    """Create an independently mutable raw-table cache."""
    return {}


def _empty_cache_stats() -> collections.Counter[str]:
    """Create an independently mutable cache-statistics counter."""
    return collections.Counter()


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
    validated = ensure_extend_value(value, path=path, key="extend")
    if isinstance(validated, str):
        return (validated,)
    return tuple(validated)


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
    parsed_table: dict[str, object] = parsed
    return parsed_table


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


def _target_directory(target: pathlib.Path) -> pathlib.Path:
    """Return the directory from which config discovery should start."""
    if target.is_dir():
        return target.expanduser().resolve()
    return target.expanduser().parent.resolve()


def _search_ancestors_for_config(directory: pathlib.Path) -> LoadedConfig | None:
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


def _split_explicit_config(
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


@dc.dataclass(slots=True)
class ConfigResolver:
    """Resolve the effective configuration for target paths.

    The resolver owns its discovery and resolved-table caches so that a single
    run reuses parsed config files across many targets without leaking mutable
    state between invocations. Construct one resolver per run; an instance is
    not safe to share across threads.
    """

    _discovery_cache: dict[pathlib.Path, pathlib.Path | None] = dc.field(
        default_factory=_empty_discovery_cache, init=False
    )
    _resolved_table_cache: dict[pathlib.Path, dict[str, object]] = dc.field(
        default_factory=_empty_resolved_table_cache, init=False
    )
    _raw_table_cache: dict[pathlib.Path, cabc.Mapping[str, object]] = dc.field(
        default_factory=_empty_raw_table_cache, init=False
    )
    _cache_stats: collections.Counter[str] = dc.field(
        default_factory=_empty_cache_stats, init=False
    )

    @property
    def cache_stats(self) -> dict[str, int]:
        """Cache hit/miss counts accumulated over this resolver's run.

        Keys include ``discovery_hits``/``discovery_misses`` for nearest-config
        discovery and ``resolved_table_hits``/``resolved_table_misses`` for
        parsed-table resolution. Absent keys imply a count of zero.

        Returns
        -------
        dict[str, int]
            Copy of the accumulated cache hit and miss counts.
        """
        return dict(self._cache_stats)

    def resolve_config_for_path(
        self,
        target: pathlib.Path,
        *,
        cli_overrides: cabc.Mapping[str, object] | None,
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        isolated: bool,
    ) -> StilyagiConfig:
        """Resolve the effective config for one target path.

        Parameters
        ----------
        target:
            The file or directory whose nearest configuration is resolved.
        cli_overrides:
            Highest-precedence overrides from command-line flags, or ``None``.
        explicit_config:
            Explicit ``--config`` values (file paths or inline TOML fragments)
            layered over the discovered config, or ``None``.
        isolated:
            When ``True``, skip nearest-config discovery and use only the
            explicit config and CLI overrides.

        Returns
        -------
        StilyagiConfig
            The merged, validated configuration for ``target``.
        """
        resolved_table: dict[str, object] = {}

        if not isolated:
            discovered_path = self._discover_nearest_config(_target_directory(target))
            if discovered_path is not None:
                resolved_table = self._resolve_config_table(discovered_path)

        resolved_table = self._merge_explicit_configs(
            resolved_table, explicit_config, target=target
        )

        if cli_overrides:
            resolved_table = _merge_config_tables(resolved_table, dict(cli_overrides))

        return parse_config_table(resolved_table, path=target)

    def _resolve_config_table(
        self,
        path: pathlib.Path,
        *,
        stack: tuple[pathlib.Path, ...] = (),
    ) -> dict[str, object]:
        """Resolve a config file and its explicit `extend` chain."""
        resolved_path = path.expanduser().resolve()
        if resolved_path in stack:
            cycle = " -> ".join(str(item) for item in (*stack, resolved_path))
            raise InvalidConfigError(path, "extend", f"cycle detected: {cycle}")

        cached = self._resolved_table_cache.get(resolved_path)
        if cached is not None:
            self._cache_stats["resolved_table_hits"] += 1
            return cached
        self._cache_stats["resolved_table_misses"] += 1

        config_table = dict(self._raw_config_table(resolved_path))
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
            parent_table = self._resolve_config_table(parent_path, stack=next_stack)
            merged = _merge_config_tables(merged, parent_table)

        merged = _merge_config_tables(merged, config_table)
        self._resolved_table_cache[resolved_path] = merged
        return merged

    def _raw_config_table(
        self, resolved_path: pathlib.Path
    ) -> cabc.Mapping[str, object]:
        """Return the raw config table, reusing the read from discovery."""
        cached = self._raw_table_cache.get(resolved_path)
        if cached is not None:
            _LOGGER.debug("reusing discovered config table for %s", resolved_path)
            return cached
        return load_config_table(resolved_path)

    def _discover_nearest_config(self, directory: pathlib.Path) -> pathlib.Path | None:
        """Return the nearest supported config file for one directory."""
        if directory in self._discovery_cache:
            self._cache_stats["discovery_hits"] += 1
            _LOGGER.debug("config discovery cache hit for %s", directory)
            return self._discovery_cache[directory]
        self._cache_stats["discovery_misses"] += 1

        discovered = _search_ancestors_for_config(directory)
        if discovered is None:
            self._discovery_cache[directory] = None
            _LOGGER.debug("no nearest config discovered from %s", directory)
            return None

        # Reuse the read performed during discovery so resolving this config
        # does not re-read the same file on the hot path.
        resolved_path = discovered.path.expanduser().resolve()
        self._raw_table_cache.setdefault(resolved_path, discovered.raw_table)
        self._discovery_cache[directory] = discovered.path
        _LOGGER.debug("discovered nearest config %s", discovered.path)
        return discovered.path

    def _merge_explicit_configs(
        self,
        resolved_table: dict[str, object],
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        *,
        target: pathlib.Path,
    ) -> dict[str, object]:
        """Layer explicit config files, then inline fragments, over one table."""
        explicit_paths, explicit_inline = _split_explicit_config(explicit_config)

        for config_path in explicit_paths:
            resolved_table = _merge_config_tables(
                resolved_table, self._resolve_config_table(config_path)
            )

        for fragment in explicit_inline:
            resolved_table = _merge_config_tables(
                resolved_table, _load_inline_config(fragment, path=target)
            )

        return resolved_table


def resolve_config_for_path(
    target: pathlib.Path,
    *,
    cli_overrides: cabc.Mapping[str, object] | None,
    explicit_config: cabc.Iterable[str | pathlib.Path] | None,
    isolated: bool,
) -> StilyagiConfig:
    """Resolve the effective config for one target with a single-use resolver.

    Each call builds a fresh :class:`ConfigResolver`, so no configuration cache
    is shared across invocations. Callers that resolve many targets in one run
    should construct one :class:`ConfigResolver` and reuse it to benefit from
    its caches.

    Parameters
    ----------
    target:
        The file or directory whose nearest configuration is resolved.
    cli_overrides:
        Highest-precedence overrides from command-line flags, or ``None``.
    explicit_config:
        Explicit ``--config`` values (file paths or inline TOML fragments)
        layered over the discovered config, or ``None``.
    isolated:
        When ``True``, skip nearest-config discovery and use only the explicit
        config and CLI overrides.

    Returns
    -------
    StilyagiConfig
        The merged, validated configuration for ``target``.
    """
    return ConfigResolver().resolve_config_for_path(
        target,
        cli_overrides=cli_overrides,
        explicit_config=explicit_config,
        isolated=isolated,
    )
