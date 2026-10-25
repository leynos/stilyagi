"""Translate parsed command-line options into resolved configuration.

Both the discovery pass and the per-file check pass need the same translation,
and they resolve it for different paths. Keeping it here lets the check
pipeline resolve one file's configuration without importing the command module,
so the dependency direction stays inward: `cli` and `check_execution` both depend
on this module, and neither depends on the other.
"""

import pathlib
import typing as typ

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
    return _build_rule_selection_overrides(
        select=options.select,
        ignore=options.ignore,
        extend_select=options.extend_select,
    )


def _build_rule_selection_overrides(
    *,
    select: tuple[str, ...],
    ignore: tuple[str, ...],
    extend_select: tuple[str, ...],
) -> dict[str, object]:
    """Translate rule selection flags to one nested config override.

    Parameters
    ----------
    select:
        Rule prefixes that replace the configured selection.
    ignore:
        Rule prefixes that replace the configured ignore list.
    extend_select:
        Rule prefixes appended after ``select`` when both are supplied.

    Returns
    -------
    dict[str, object]
        The nested ``lint`` mapping implied by the flags, or an empty mapping
        when no selection flag is present.

    Examples
    --------
    >>> _build_rule_selection_overrides(
    ...     select=("STY",), ignore=(), extend_select=("DOC",)
    ... )
    {'lint': {'select': ('STY', 'DOC')}}
    >>> _build_rule_selection_overrides(select=(), ignore=(), extend_select=())
    {}
    """
    lint_overrides: dict[str, object] = {}
    if select:
        lint_overrides["select"] = select
    if ignore:
        lint_overrides["ignore"] = ignore
    if extend_select:
        lint_select = typ.cast("tuple[str, ...]", lint_overrides.get("select", ()))
        lint_overrides["select"] = (*lint_select, *extend_select)

    return {"lint": lint_overrides} if lint_overrides else {}


def resolve_target_config(
    target: pathlib.Path,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the effective config for one target path.

    Returns
    -------
    config.StilyagiConfig
        The configuration in force for ``target``, with the command-line
        overrides applied over whatever the discovered config files provide.
    """
    return resolver.resolve_config_for_path(
        target,
        cli_overrides=build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


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
