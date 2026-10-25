"""Configuration resolution helpers for Stilyagi."""

import collections
import collections.abc as cabc
import dataclasses as dc
import logging
import typing as typ

from .inspection import _build_config_inspection, _ConfigInspection
from .load import discover_same_directory_config, load_config_table
from .parse import parse_config_table
from .provenance import (
    _apply_cli_layer,
    _config_table_from_layer,
    _ConfigOrigin,
    _ConfigTableWithOrigins,
    _load_inline_config,
    _merge_config_tables,
    _merge_config_tables_with_origins,
    _normalise_extend_values,
    _resolve_config_reference,
    _split_explicit_config,
)
from .schema import InvalidConfigError, StilyagiConfig

if typ.TYPE_CHECKING:
    import pathlib

    from .load import LoadedConfig

_LOGGER = logging.getLogger(__name__)


def _empty_discovery_cache() -> dict[pathlib.Path, pathlib.Path | None]:
    """Create an independently mutable discovery cache."""
    return {}


def _empty_resolved_table_cache() -> dict[pathlib.Path, dict[str, object]]:
    """Create an independently mutable resolved-table cache."""
    return {}


def _empty_provenance_cache() -> dict[pathlib.Path, _ConfigTableWithOrigins]:
    """Create an independently mutable resolved-origin cache."""
    return {}


def _empty_raw_table_cache() -> dict[pathlib.Path, cabc.Mapping[str, object]]:
    """Create an independently mutable raw-table cache."""
    return {}


def _empty_cache_stats() -> collections.Counter[str]:
    """Create an independently mutable cache-statistics counter."""
    return collections.Counter()


def _target_directory(target: pathlib.Path) -> pathlib.Path:
    """Return the directory from which config discovery should start."""
    if target.is_dir():
        return target.expanduser().resolve()
    return target.expanduser().parent.resolve()


def _search_ancestors_for_config(
    directory: pathlib.Path,
) -> LoadedConfig | None:
    """Walk from a directory to the filesystem root looking for config."""
    current = directory
    while True:
        discovered = discover_same_directory_config(current)
        if discovered is not None:
            return discovered
        if current.parent == current:
            return None
        current = current.parent


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
    _provenance_cache: dict[pathlib.Path, _ConfigTableWithOrigins] = dc.field(
        default_factory=_empty_provenance_cache, init=False
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

    def _inspect_config_for_path(
        self,
        target: pathlib.Path,
        *,
        cli_overrides: cabc.Mapping[str, object] | None,
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        isolated: bool,
    ) -> _ConfigInspection:
        """Resolve one target's effective config and source ledger."""
        resolved = _ConfigTableWithOrigins(values={}, origins={})
        if not isolated:
            discovered_path = self._discover_nearest_config(_target_directory(target))
            if discovered_path is not None:
                resolved = self._resolve_config_table_with_origins(discovered_path)

        explicit_paths, explicit_inline = _split_explicit_config(explicit_config)
        for config_path in explicit_paths:
            resolved = _merge_config_tables_with_origins(
                resolved,
                self._resolve_config_table_with_origins(config_path),
            )

        for fragment in explicit_inline:
            inline_table = _load_inline_config(fragment, path=target)
            resolved = _apply_cli_layer(resolved, inline_table, kind="inline")

        if cli_overrides:
            resolved = _apply_cli_layer(
                resolved,
                dict(cli_overrides),
                kind="flag",
            )

        return _build_config_inspection(resolved, target=target)

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

    def _resolve_config_table_with_origins(
        self,
        path: pathlib.Path,
        *,
        stack: tuple[pathlib.Path, ...] = (),
    ) -> _ConfigTableWithOrigins:
        """Resolve one file layer and retain each value's defining source."""
        resolved_path = path.expanduser().resolve()
        if resolved_path in stack:
            cycle = " -> ".join(str(item) for item in (*stack, resolved_path))
            raise InvalidConfigError(path, "extend", f"cycle detected: {cycle}")

        cached = self._provenance_cache.get(resolved_path)
        if cached is not None:
            return cached

        table = dict(self._raw_config_table(resolved_path))
        extend_values = _normalise_extend_values(
            table.get("extend"), path=resolved_path
        )
        merged = _ConfigTableWithOrigins(values={}, origins={})
        next_stack = (*stack, resolved_path)
        for extend_value in extend_values:
            parent_path = _resolve_config_reference(
                extend_value,
                base_directory=resolved_path.parent,
                path=resolved_path,
            )
            parent = self._resolve_config_table_with_origins(
                parent_path,
                stack=next_stack,
            )
            merged = _merge_config_tables_with_origins(merged, parent)

        file_layer = _config_table_from_layer(
            table,
            _ConfigOrigin("file", resolved_path, cli_overridden=False),
        )
        merged = _merge_config_tables_with_origins(merged, file_layer)
        self._provenance_cache[resolved_path] = merged
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
