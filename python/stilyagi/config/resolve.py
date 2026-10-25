"""Configuration resolution helpers for Stilyagi.

Resolution has two consumers with different needs. The check pipeline wants one
target's effective configuration and the file that supplied it, so a diagnostic
can name the config it was produced under. The inspection command wants the
same values with the origin of each leaf. One resolution pass answers both, so
precedence and file reads cannot drift between them.
"""

import collections
import collections.abc as cabc
import dataclasses as dc
import logging
import typing as typ

from .inspection import _build_config_inspection, _ConfigInspection
from .load import load_config_table
from .parse import parse_config_table
from .path_resolution import expand_and_resolve
from .provenance import (
    _apply_cli_layer,
    _config_table_from_layer,
    _ConfigOrigin,
    _ConfigTableWithOrigins,
    _merge_config_tables_with_origins,
)
from .schema import InvalidConfigError, StilyagiConfig
from .tables import (
    load_inline_config,
    normalize_extend_values,
    resolve_config_reference,
    search_ancestors_for_config,
    split_explicit_config,
    target_directory,
)

if typ.TYPE_CHECKING:
    import pathlib

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class ResolvedTargetConfig:
    """One target's effective config together with the file that supplied it.

    Rule execution needs both halves together: the configuration itself, and
    the provenance a diagnostic reports. Resolving them once, in one pass,
    stops a caller from re-deriving one half and disagreeing with the other.

    Attributes
    ----------
    config:
        The configuration in force for the target, with command-line overrides
        applied over whatever the discovered config files provide.
    config_file:
        The config file that governs the target, or ``None`` when only inline
        configuration and built-in defaults apply.

    Examples
    --------
    >>> ResolvedTargetConfig(StilyagiConfig(), None).config_file is None
    True
    """

    config: StilyagiConfig
    config_file: pathlib.Path | None


@dc.dataclass(frozen=True, slots=True)
class _ConfigResolution:
    """One target's value ledger together with the file that governs it."""

    table: _ConfigTableWithOrigins
    config_file: pathlib.Path | None


@dc.dataclass(slots=True)
class ConfigResolver:
    """Resolve the effective configuration for target paths.

    The resolver owns its discovery and resolved-table caches so that a single
    run reuses parsed config files across many targets without leaking mutable
    state between invocations. Construct one resolver per run; an instance is
    not safe to share across threads.
    """

    # Each factory is a fresh `dict` or `Counter`, so the built-in callables
    # give every instance its own empty container.
    _discovery_cache: dict[pathlib.Path, pathlib.Path | None] = dc.field(
        default_factory=dict, init=False
    )
    _resolved_table_cache: dict[pathlib.Path, _ConfigTableWithOrigins] = dc.field(
        default_factory=dict, init=False
    )
    _raw_table_cache: dict[pathlib.Path, cabc.Mapping[str, object]] = dc.field(
        default_factory=dict, init=False
    )
    _cache_stats: collections.Counter[str] = dc.field(
        default_factory=collections.Counter, init=False
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
        return self.resolve_with_provenance(
            target,
            cli_overrides=cli_overrides,
            explicit_config=explicit_config,
            isolated=isolated,
        ).config

    def resolve_with_provenance(
        self,
        target: pathlib.Path,
        *,
        cli_overrides: cabc.Mapping[str, object] | None,
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        isolated: bool,
    ) -> ResolvedTargetConfig:
        """Resolve one target's config and the file that supplied it, in one pass.

        The effective config file is the last explicit ``--config`` path, since
        explicit files are layered in order and the last has the final say.
        Otherwise it is the nearest discovered config, unless ``isolated``
        suppressed discovery. An inline fragment names no file, so it supplies
        no provenance.

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
        ResolvedTargetConfig
            The validated configuration for ``target`` and the config file
            that governs it, or ``None`` when only inline configuration and
            built-in defaults apply.

        Examples
        --------
        >>> from pathlib import Path
        >>> resolved = ConfigResolver().resolve_with_provenance(
        ...     Path("/work/docs/a.md"),
        ...     cli_overrides=None,
        ...     explicit_config=None,
        ...     isolated=True,
        ... )
        >>> resolved.config_file is None
        True
        """
        resolved = self._resolve_config_for_path(
            target,
            cli_overrides=cli_overrides,
            explicit_config=explicit_config,
            isolated=isolated,
        )
        return ResolvedTargetConfig(
            config=parse_config_table(resolved.table.values, path=target),
            config_file=resolved.config_file,
        )

    def _inspect_config_for_path(
        self,
        target: pathlib.Path,
        *,
        cli_overrides: cabc.Mapping[str, object] | None,
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        isolated: bool,
    ) -> _ConfigInspection:
        """Resolve one target's effective config and source ledger."""
        resolved = self._resolve_config_for_path(
            target,
            cli_overrides=cli_overrides,
            explicit_config=explicit_config,
            isolated=isolated,
        )
        return _build_config_inspection(resolved.table, target=target)

    def _resolve_config_for_path(
        self,
        target: pathlib.Path,
        *,
        cli_overrides: cabc.Mapping[str, object] | None,
        explicit_config: cabc.Iterable[str | pathlib.Path] | None,
        isolated: bool,
    ) -> _ConfigResolution:
        """Resolve one target to its values, their origins, and their file."""
        # Split once: a one-shot iterator would otherwise be exhausted first.
        explicit_paths, explicit_inline = split_explicit_config(explicit_config)
        discovered_path: pathlib.Path | None = None
        resolved = _ConfigTableWithOrigins(values={}, origins={})

        if not isolated:
            discovered_path = self._discover_nearest_config(target_directory(target))
            if discovered_path is not None:
                resolved = self._resolve_config_table(discovered_path)

        resolved = self._merge_explicit_configs(
            resolved,
            explicit_paths,
            explicit_inline,
            target=target,
        )

        if cli_overrides:
            resolved = _apply_cli_layer(resolved, dict(cli_overrides), kind="flag")

        return _ConfigResolution(
            table=resolved,
            config_file=explicit_paths[-1] if explicit_paths else discovered_path,
        )

    def _resolve_config_table(
        self,
        path: pathlib.Path,
        *,
        stack: tuple[pathlib.Path, ...] = (),
    ) -> _ConfigTableWithOrigins:
        """Resolve one config file and its `extend` chain with origins."""
        resolved_path = expand_and_resolve(path)
        if resolved_path in stack:
            cycle = " -> ".join(str(item) for item in (*stack, resolved_path))
            raise InvalidConfigError(path, "extend", f"cycle detected: {cycle}")

        cached = self._resolved_table_cache.get(resolved_path)
        if cached is not None:
            self._cache_stats["resolved_table_hits"] += 1
            return cached
        self._cache_stats["resolved_table_misses"] += 1

        table = dict(self._raw_config_table(resolved_path))
        extend_values = normalize_extend_values(table.get("extend"), path=resolved_path)
        merged = _ConfigTableWithOrigins(values={}, origins={})
        next_stack = (*stack, resolved_path)
        for extend_value in extend_values:
            parent_path = resolve_config_reference(
                extend_value,
                base_directory=resolved_path.parent,
                path=resolved_path,
            )
            merged = _merge_config_tables_with_origins(
                merged,
                self._resolve_config_table(parent_path, stack=next_stack),
            )

        merged = _merge_config_tables_with_origins(
            merged,
            _config_table_from_layer(
                table,
                _ConfigOrigin("file", resolved_path, cli_overridden=False),
            ),
        )
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

        discovered = search_ancestors_for_config(directory)
        if discovered is None:
            self._discovery_cache[directory] = None
            _LOGGER.debug("no nearest config discovered from %s", directory)
            return None

        # Reuse the read performed during discovery so resolving this config
        # does not re-read the same file on the hot path.
        resolved_path = expand_and_resolve(discovered.path)
        self._raw_table_cache.setdefault(resolved_path, discovered.raw_table)
        self._discovery_cache[directory] = discovered.path
        _LOGGER.debug("discovered nearest config %s", discovered.path)
        return discovered.path

    def _merge_explicit_configs(
        self,
        resolved: _ConfigTableWithOrigins,
        explicit_paths: cabc.Iterable[pathlib.Path],
        explicit_inline: cabc.Iterable[str],
        *,
        target: pathlib.Path,
    ) -> _ConfigTableWithOrigins:
        """Layer explicit config files, then inline fragments, over one table."""
        for config_path in explicit_paths:
            resolved = _merge_config_tables_with_origins(
                resolved,
                self._resolve_config_table(config_path),
            )

        for fragment in explicit_inline:
            resolved = _apply_cli_layer(
                resolved,
                load_inline_config(fragment, path=target),
                kind="inline",
            )

        return resolved


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
