"""Translate parsed command-line options into resolved configuration.

Both the discovery pass and the per-file check pass need the same translation,
and they resolve it for different paths. Keeping it here lets the check
pipeline resolve one file's configuration without importing the command module,
so the dependency direction stays inward: `cli` and `check_execution` both depend
on this module, and neither depends on the other.
"""

import pathlib
import typing as typ

from stilyagi.config import rules as rule_options

__all__ = [
    "build_cli_overrides",
    "resolve_discovery_config",
    "resolve_target_config",
]

if typ.TYPE_CHECKING:
    from stilyagi import config
    from stilyagi.cli_args import CheckOptions


def build_cli_overrides(options: CheckOptions) -> dict[str, object]:
    """Return config overrides extracted from command-line options.

    ``--extend-select`` appends to whatever ``--select`` already contributed,
    so the two flags combine into one selection rather than replacing it.

    Returns
    -------
    dict[str, object]
        The nested ``lint`` overrides implied by the parsed options, empty when
        the options request nothing.

    Examples
    --------
    >>> from stilyagi.cli_args import CheckOptions
    >>> build_cli_overrides(CheckOptions(targets=("docs",), select=("STY",)))
    {'lint': {'select': ('STY',)}}
    >>> build_cli_overrides(CheckOptions(targets=("docs",)))
    {}
    """
    lint_overrides: dict[str, object] = {}
    if options.select:
        lint_overrides["select"] = options.select
    if options.ignore:
        lint_overrides["ignore"] = options.ignore
    if options.extend_select:
        lint_select = typ.cast(
            "tuple[str, ...]",
            lint_overrides.get("select", ()),
        )
        lint_overrides["select"] = (*lint_select, *options.extend_select)

    overrides: dict[str, object] = {}
    if lint_overrides:
        overrides["lint"] = lint_overrides
    return overrides


def resolve_target_config(
    target: pathlib.Path,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve and validate the effective config for one target path.

    Per-rule tables are validated here rather than only when a rule runs, so a
    malformed option is reported the same way whether or not its rule is
    selected. A malformed table raises :class:`config.InvalidConfigError`; the
    error names the config file that governs the target when one does, and
    falls back to the target path for an inline-only configuration.

    Parameters
    ----------
    target:
        The file or directory whose effective configuration is resolved.
    options:
        Parsed command-line options supplying overrides and explicit config.
    resolver:
        The run's shared configuration resolver.

    Returns
    -------
    config.StilyagiConfig
        The configuration in force for ``target``, with the command-line
        overrides applied over whatever the discovered config files provide.
    """
    resolved = resolver.resolve_config_for_path(
        target,
        cli_overrides=build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )
    config_file = resolver.config_file_for_path(
        target,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )
    rule_options.validate_builtin_tables(resolved, path=config_file or target)
    return resolved


def resolve_discovery_config(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the configuration that governs Markdown discovery.

    Discovery is a single pass over every target, so it is governed by the
    configuration resolved for the current working directory rather than by any
    individual file's nearest config. Resolving it here keeps ``--isolated``,
    explicit ``--config`` values, and CLI overrides in force during discovery.

    Returns
    -------
    config.StilyagiConfig
        The configuration used to discover Markdown inputs.
    """
    return resolve_target_config(pathlib.Path(), options, resolver)
