"""Per-input execution stages for the `stilyagi check` command."""

import logging
import pathlib
import tokenize
import typing as typ

from stilyagi import check_metrics, config, diagnostics, engine, model
from stilyagi.check_inputs import (
    CheckInput,
    DiscoveryOutcome,
    FileCheckResult,
    report_check_error,
    report_file_error,
)
from stilyagi.engine.checker import map_ir_errors
from stilyagi.rules import registry as rules_registry

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import CheckOptions

_LOGGER = logging.getLogger(__name__)


def _build_cli_overrides(options: CheckOptions) -> dict[str, object]:
    """Return config overrides extracted from command-line options."""
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


def _resolve_config(
    target: pathlib.Path,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the effective config for one target path."""
    return resolver.resolve_config_for_path(
        target,
        cli_overrides=_build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


def _resolve_discovery_config(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the command config that governs the single discovery pass."""
    return resolver.resolve_config_for_path(
        pathlib.Path(),
        cli_overrides=_build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


def _check_discovered_files(
    check_inputs: cabc.Iterable[CheckInput],
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> DiscoveryOutcome:
    """Check every input and accumulate diagnostics and operational outcomes."""
    had_error = False
    unreadable_files = 0
    diagnostics_list: list[diagnostics.Diagnostic] = []
    for check_input in check_inputs:
        file_result = _check_one_file(
            check_input,
            options,
            resolver,
        )
        diagnostics_list.extend(file_result.diagnostics)
        had_error = had_error or file_result.had_error
        unreadable_files += int(file_result.was_unreadable)
    return DiscoveryOutcome(
        diagnostics=diagnostics_list,
        had_error=had_error,
        unreadable_files=unreadable_files,
    )


def _read_source(check_input: CheckInput) -> str | None:
    """Return one source text, reporting read and decoding failures."""
    try:
        source = check_input.source_text
        if source is None:
            if check_input.syntax is model.Syntax.PYTHON_DOCSTRING:
                with tokenize.open(check_input.resolved_path) as source_file:
                    source = source_file.read()
            else:
                source = check_input.resolved_path.read_text(encoding="utf-8-sig")
    except (MemoryError, OSError, SyntaxError, UnicodeDecodeError) as exc:
        report_file_error(check_input.reported_path, exc)
        return None
    return source


def _check_one_file(
    check_input: CheckInput,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> FileCheckResult:
    """Check one input and report operational and read-failure outcomes."""
    check_metrics._record_file(check_input.syntax)
    with check_metrics._measure_phase("read"):
        source = _read_source(check_input)
    if source is None:
        check_metrics.record_unreadable_file()
        check_metrics.record_operational_failure("read")
        return FileCheckResult(diagnostics=[], had_error=True, was_unreadable=True)

    _LOGGER.debug("extracting %s", check_input.reported_path)
    try:
        with check_metrics._measure_phase("extract"):
            document = engine.extract_document(source, check_input.syntax)
    except engine.BridgeExtractionError as exc:
        check_metrics.record_operational_failure("extract")
        report_check_error(check_input.reported_path, exc)
        return FileCheckResult(diagnostics=[], had_error=True, was_unreadable=False)
    except Exception:
        check_metrics.record_operational_failure("extract")
        _LOGGER.exception(
            "unexpected extraction failure for %s",
            check_input.reported_path,
        )
        raise

    _LOGGER.debug("resolving config for %s", check_input.reported_path)
    try:
        with check_metrics._measure_phase("config"):
            resolved_config = _resolve_config(
                check_input.resolved_path, options, resolver
            )
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
    ) as exc:
        check_metrics.record_operational_failure("config")
        report_check_error(check_input.reported_path, exc)
        return FileCheckResult(diagnostics=[], had_error=True, was_unreadable=False)

    try:
        with check_metrics._measure_phase("rules"):
            diagnostics_list = [
                *map_ir_errors(document, check_input.reported_path),
                *rules_registry.run_rules(document, resolved_config),
            ]
    except Exception:
        check_metrics.record_operational_failure("rules")
        raise
    return FileCheckResult(
        diagnostics=diagnostics_list,
        had_error=False,
        was_unreadable=False,
    )
