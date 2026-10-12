"""Command-line interface for Stilyagi.

The check command discovers registered source files, reads each input,
extracts documents through the Rust bridge, and renders the accumulated
diagnostics with an honest run summary.
"""

import logging
import pathlib
import sys
import typing as typ

from stilyagi import check_metrics, config, diagnostics, discovery, engine, model
from stilyagi.check_execution import (
    _check_discovered_files,
    _resolve_discovery_config,
)
from stilyagi.check_inputs import (
    CheckInput,
    DiscoveryInputs,
    configure_command_warning_handler,
    report_check_error,
    report_discovery_outcomes,
)
from stilyagi.cli_args import (
    PACKAGE_VERSION,
    CheckOptions,
    build_parser,
    options_from_args,
)
from stilyagi.discovery_results import SkippedCandidateCount

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = [
    "PACKAGE_VERSION",
    "CheckInput",
    "CheckOptions",
    "build_parser",
    "compute_exit_code",
    "main",
    "run_check",
]

_LOGGER = logging.getLogger(__name__)


def _configure_logging(options: CheckOptions) -> None:
    """Configure verbosity and isolate warning output from root handlers."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.WARNING)
    if options.silent or options.quiet:
        root_logger.setLevel(logging.WARNING)
    elif options.verbose:
        root_logger.setLevel(logging.INFO)

    configure_command_warning_handler()


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the Stilyagi command-line interface.

    Returns
    -------
    int
        The command exit status.

    Examples
    --------
    >>> main(["check", "--version"])  # doctest: +SKIP
    0
    """
    normalized_argv = tuple(sys.argv[1:] if argv is None else argv)
    if not normalized_argv:
        normalized_argv = ("check",)

    parser = build_parser()
    try:
        args = parser.parse_args(list(normalized_argv))
    except SystemExit as exc:
        return typ.cast("int", exc.code)

    options = options_from_args(args)
    return run_check(options)


def run_check(
    options: CheckOptions,
    *,
    resolver: config.ConfigResolver | None = None,
    renderer: engine.RendererRegistry | None = None,
) -> int:
    """Run the check command and print rendered diagnostics.

    Parameters
    ----------
    options:
        The parsed options for one `check` invocation.
    resolver:
        Resolver shared between checked files; new when not supplied.
    renderer:
        Renderer used to serialise diagnostics. Defaults to a new
        :class:`~stilyagi.engine.RendererRegistry`.

    Returns
    -------
    int
        Zero when the check succeeds or produces warnings, one when it
        produces failing diagnostics, or two when an operational error occurs.
    """
    _configure_logging(options)
    check_metrics.reset_check_metrics()
    resolver = resolver if resolver is not None else config.ConfigResolver()
    renderer = renderer if renderer is not None else engine.RendererRegistry()
    _LOGGER.debug("target discovery started for %r", options.targets)
    try:
        with check_metrics._measure_phase("discovery"):
            discovery_inputs = _discover_targets(options, resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
        ValueError,
    ) as error:
        check_metrics.record_operational_failure(
            "config"
            if isinstance(
                error, (config.InvalidCacheDirError, config.InvalidConfigError)
            )
            else "discovery"
        )
        report_check_error(None, error)
        return check_metrics._finish_check(
            2,
            verbose=options.verbose,
        )
    except Exception:
        check_metrics.record_operational_failure("discovery")
        check_metrics._finish_check(
            2,
            verbose=options.verbose,
        )
        raise
    _report_discovery_outcomes(discovery_inputs)
    _LOGGER.debug(
        "target discovery finished: %d input(s)",
        len(discovery_inputs.inputs),
    )

    return _check_and_render(
        discovery_inputs,
        options,
        resolver,
        renderer,
    )


def _report_discovery_outcomes(discovery_inputs: DiscoveryInputs) -> None:
    """Report discovery events and record their bounded operational metrics."""
    check_metrics._record_skips(discovery_inputs.skipped_by_reason)
    for _failure in discovery_inputs.failures:
        check_metrics.record_operational_failure("discovery")
    report_discovery_outcomes(discovery_inputs)


def _check_and_render(
    discovery_inputs: DiscoveryInputs,
    options: CheckOptions,
    resolver: config.ConfigResolver,
    renderer: engine.RendererRegistry,
) -> int:
    """Check discovered inputs, render the summary and finalize metrics."""
    check_outcome = _check_discovered_files(
        discovery_inputs.inputs,
        options,
        resolver,
    )
    _LOGGER.debug(
        "rendering %d diagnostic(s) as %s",
        len(check_outcome.diagnostics),
        options.output_format,
    )
    summary = engine.RunSummary.from_diagnostics(
        check_outcome.diagnostics,
        checked_files=len(discovery_inputs.inputs),
        skipped_files=discovery_inputs.skipped_files,
        unreadable_files=check_outcome.unreadable_files,
    )
    check_metrics._record_diagnostic_counts(summary.errors, summary.warnings)
    try:
        with check_metrics._measure_phase("render"):
            print(
                renderer.render(
                    check_outcome.diagnostics,
                    options.output_format,
                    summary,
                ),
                end="",
            )
    except Exception:
        check_metrics.record_operational_failure("render")
        check_metrics._finish_check(
            2,
            verbose=options.verbose,
        )
        raise
    exit_code = compute_exit_code(
        check_outcome.diagnostics,
        had_error=bool(discovery_inputs.failures) or check_outcome.had_error,
    )
    _LOGGER.info("config resolver cache stats: %s", resolver.cache_stats)
    _LOGGER.debug("check complete: exit code %d", exit_code)
    return check_metrics._finish_check(
        exit_code,
        verbose=options.verbose,
    )


def compute_exit_code(
    diagnostics_list: cabc.Sequence[diagnostics.Diagnostic],
    *,
    had_error: bool = False,
) -> int:
    """Return the documented exit code for one check run.

    Returns
    -------
    int
        Zero for success or warning-only diagnostics, one for error-severity
        diagnostics, or two for an operational error.

    Examples
    --------
    >>> compute_exit_code([])
    0
    >>> compute_exit_code([
    ...     diagnostics.Diagnostic(path="docs/example.md", code="STY001", message="x")
    ... ])
    1
    >>> compute_exit_code([
    ...     diagnostics.Diagnostic(
    ...         path="docs/example.md",
    ...         code="IR001",
    ...         message="x",
    ...         severity=diagnostics.Severity.WARNING,
    ...     )
    ... ])
    0
    >>> compute_exit_code([], had_error=True)
    2
    """
    if had_error:
        return 2
    if any(diagnostics.is_failing_severity(item.severity) for item in diagnostics_list):
        return 1
    return 0


def _discover_targets(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> DiscoveryInputs:
    """Discover registered files beneath the requested targets."""
    target_paths = [pathlib.Path(target) for target in options.targets]
    has_stdin_target = any(target.as_posix() == "-" for target in target_paths)
    if has_stdin_target and len(target_paths) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    if has_stdin_target:
        check_input = _stdin_check_input(options.stdin_filename)
        return DiscoveryInputs(
            inputs=() if check_input is None else (check_input,),
            skipped_files=int(check_input is None),
            skipped_by_reason=(
                (SkippedCandidateCount("unregistered_candidate", 1),)
                if check_input is None
                else ()
            ),
        )
    discovery_config = _resolve_discovery_config(options, resolver)
    result = discovery.discover_files_with_summary(
        target_paths,
        discovery_config,
    )
    return DiscoveryInputs(
        inputs=tuple(CheckInput.from_discovered(file) for file in result.files),
        skipped_files=result.skipped_files,
        notices=result.notices,
        failures=result.failures,
        skipped_by_reason=result.skipped_by_reason,
    )


def _stdin_check_input(stdin_filename: str | None) -> CheckInput | None:
    """Build the check input that consumes standard input."""
    syntax = (
        model.Syntax.MARKDOWN
        if stdin_filename is None
        else discovery.syntax_for_path(pathlib.Path(stdin_filename))
    )
    if syntax is None:
        report_check_error(
            None,
            ValueError(
                f"skipping stdin without a registered extractor: {stdin_filename}"
            ),
        )
        return None
    reported_path = (
        pathlib.Path(stdin_filename).as_posix() if stdin_filename else "<stdin>"
    )
    resolved_path = (
        pathlib.Path(stdin_filename) if stdin_filename else pathlib.Path("<stdin>")
    )
    return CheckInput(
        reported_path=reported_path,
        resolved_path=resolved_path,
        syntax=syntax,
        source_text=sys.stdin.read(),
    )
