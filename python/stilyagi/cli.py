"""Command-line interface for Stilyagi.

The check command discovers registered source files, reads each input,
extracts documents through the Rust bridge, and renders the accumulated
diagnostics with an honest run summary. The config command inspects effective
values and their source origins without linting files.
The dump-ir command emits the canonical Rust JSON for Markdown inputs.

The command is an orchestration layer and nothing more. Target resolution,
per-file checking, aggregation, fix execution, rendering and the exit policy
each live in their own module; what stays here is the sequence that binds them
and the collaborator bundle that lets a test substitute one boundary.

`compute_exit_code` is re-exported rather than reimplemented: RFC 0003 §12
defines the mapping from diagnostics to process status, and it is documented at
`cli.compute_exit_code`, but the single implementation lives in
`check_outcome` beside the report it describes.
"""

import dataclasses as dc
import logging
import sys
import time
import typing as typ

from stilyagi import (
    check_metrics,
    cli_apply,
    cli_log,
    config,
    engine,
)
from stilyagi.check_execution import CheckReporter, CheckRun, check_one_file
from stilyagi.check_inputs import (
    CheckInput,
    DiscoveryInputs,
    report_discovery_outcomes,
)
from stilyagi.check_outcome import compute_exit_code, report_run
from stilyagi.check_targets import discover_targets
from stilyagi.cli_args import (
    PACKAGE_VERSION,
    CheckOptions,
    _config_inspection_options_from_args,
    build_parser,
    dump_ir_options_from_args,
    options_from_args,
)
from stilyagi.cli_config_command import _run_config_inspection
from stilyagi.cli_dump_ir import run_dump_ir
from stilyagi.cli_io import report_check_error
from stilyagi.cli_run import CheckedFile
from stilyagi.rules import registry as rules_registry

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = [
    "PACKAGE_VERSION",
    "CheckCollaborators",
    "CheckInput",
    "CheckOptions",
    "build_parser",
    "compute_exit_code",
    "main",
    "run_check",
]

_LOGGER = logging.getLogger(__name__)

#: The usage error reported when a mutating and a non-mutating flag are
#: combined. Named so the message and the RFC 0003 §10 amendment cannot drift.
_FIX_DIFF_CONFLICT = "--fix and --diff cannot be combined"


@dc.dataclass(frozen=True, slots=True)
class CheckCollaborators:
    """Injectable collaborators for one check run.

    The bundle keeps the public check entry point small while allowing tests to
    substitute one boundary without coupling themselves to pipeline internals.
    Omitting a field uses its production default for this run.

    The defaults are factories rather than ``None`` sentinels, and the factories
    run once per instance, so two `run_check` invocations never share a
    configuration cache or an output stream. A constructed bundle is therefore
    already usable: there is no half-populated state left for a second pass to
    resolve.

    Each factory resolves its target through the module at call time rather
    than capturing it at import time, so a test that substitutes a module-level
    default -- as the rule-runner contract tests do -- still takes effect. The
    two class defaults are passed as the callable itself, because constructing
    them is already the fresh-instance-per-run behaviour the fields need.

    There is no writer here. A mutating run reaches the filesystem through
    `fix_execution`, and a collaborator that no code path consulted would be a
    seam that only looks like one.
    """

    resolver: config.ConfigResolver = dc.field(default_factory=config.ConfigResolver)
    renderer: engine.RendererRegistry = dc.field(
        default_factory=engine.RendererRegistry
    )
    rule_runner: rules_registry.RuleRunner = dc.field(
        default_factory=lambda: rules_registry.run_rules
    )
    output: typ.TextIO = dc.field(default_factory=lambda: sys.stdout)
    reporter: CheckReporter = dc.field(default_factory=lambda: report_check_error)


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

    if args.command == "config":
        config_options = _config_inspection_options_from_args(args)
        return _run_config_inspection(config_options)
    if args.command == "dump-ir":
        return run_dump_ir(dump_ir_options_from_args(args))

    options = options_from_args(args)
    return run_check(options)


def run_check(
    options: CheckOptions,
    *,
    collaborators: CheckCollaborators | None = None,
) -> int:
    """Run the check command and print rendered diagnostics.

    Parameters
    ----------
    options:
        The parsed options for one `check` invocation.
    collaborators:
        Optional injected pipeline boundaries. Missing collaborators use the
        production defaults for this one run.

    Returns
    -------
    int
        Zero when the check succeeds without findings, one when diagnostics
        are found, or two when an operational error occurs.

    Examples
    --------
    >>> run_check(CheckOptions(targets=("--nope",)))  # doctest: +SKIP
    2
    """
    resolved_collaborators = collaborators or CheckCollaborators()
    if options.fix and options.diff:
        # D-06: silent precedence between a mutating and a non-mutating flag is
        # the surprise the CLI contract exists to prevent. Rejection is the
        # relaxable direction -- a rejected pair can be given meaning later,
        # where an accepted one with silent precedence cannot be withdrawn.
        #
        # This runs before `_configure_logging`, so the command handler is not
        # installed yet and the reporter's one emission would reach the
        # terminal only through `logging.lastResort` -- which the logging module
        # declines to use as soon as any handler exists in the chain, so an
        # embedding application that called `basicConfig` first would swallow
        # the message entirely. Installing the handler here makes the guarantee
        # explicit instead of incidental. It is idempotent: setup replaces only
        # the handler this function owns.
        cli_log.configure_command_warning_handler()
        resolved_collaborators.reporter(
            None,
            ValueError(_FIX_DIFF_CONFLICT),
        )
        return 2

    started_at_ns = check_metrics._start_check()
    check_metrics.reset_check_metrics()
    try:
        _configure_logging(options)
        exit_code = _run_check(options, resolved_collaborators)
    except Exception:
        check_metrics._finish_check(
            2,
            verbose=options.verbose,
            started_at_ns=started_at_ns,
        )
        raise
    return check_metrics._finish_check(
        exit_code,
        verbose=options.verbose,
        started_at_ns=started_at_ns,
    )


def _report_discovery_outcomes(discovery_inputs: DiscoveryInputs) -> None:
    """Report discovery events and record their bounded operational metrics."""
    check_metrics._record_skips(discovery_inputs.skipped_by_reason)
    for _failure in discovery_inputs.failures:
        check_metrics.record_operational_failure("discovery")
    report_discovery_outcomes(discovery_inputs)


def _configure_logging(options: CheckOptions) -> None:
    """Apply the requested verbosity level before running the check loop.

    The handler is `cli_log.log_handler`, not the stdlib default. The default
    formatter renders the log message alone and drops `extra` entirely, so a
    structured record arrived at the user as its bare sentence -- the planner's
    per-file decision printed as `fix plan decided`, with no file identity and
    none of the counters that are the reason the record exists. Installing the
    handler here rather than in an entry point keeps `--verbose` the single
    switch that decides whether any of it is shown.
    """
    cli_log.configure_command_warning_handler()
    if options.silent or options.quiet:
        logging.basicConfig(level=logging.WARNING, handlers=[cli_log.log_handler()])
    elif options.verbose:
        logging.basicConfig(level=logging.INFO, handlers=[cli_log.log_handler()])


def _run_check(
    options: CheckOptions,
    resolved_collaborators: CheckCollaborators,
) -> int:
    """Discover inputs and check them, leaving run finalization to the caller."""
    _LOGGER.debug("target discovery started for %r", options.targets)
    try:
        with check_metrics._measure_phase("discovery"):
            discovery_inputs = discover_targets(
                options, resolved_collaborators.resolver
            )
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
        resolved_collaborators.reporter(None, error)
        return 2
    except Exception:
        check_metrics.record_operational_failure("discovery")
        raise
    _report_discovery_outcomes(discovery_inputs)
    _LOGGER.debug(
        "target discovery finished: %d input(s)",
        len(discovery_inputs.inputs),
    )

    run = CheckRun(
        options=options,
        resolver=resolved_collaborators.resolver,
        rule_runner=resolved_collaborators.rule_runner,
        report=resolved_collaborators.reporter,
    )
    started = time.perf_counter()
    checked_files = [
        CheckedFile(
            reported_path=check_input.reported_path,
            result=check_one_file(check_input, run),
        )
        for check_input in discovery_inputs.inputs
    ]
    # Logged at the command boundary rather than in the planner: the planner
    # records what it *decided*, and a target it never planned -- a file with no
    # fixable diagnostic, or a stream input -- would otherwise be missing from
    # any timing record. The unit is whole-check elapsed milliseconds, covering
    # discovery, extraction, config resolution, rule running, and planning.
    _LOGGER.info(
        "check pass finished",
        extra={
            "operation": "collect_checked_files",
            "elapsed_ms": cli_apply.elapsed_ms(started),
            "checked_files": len(checked_files),
        },
    )
    if options.fix:
        applied = cli_apply.apply_fixes(
            checked_files, run, options, resolved_collaborators
        )
        # The exit policy is stated once, here, rather than in the module that
        # performs the writes: a write failure is an operational error even when
        # the re-lint found nothing left to report, and that coupling is a
        # command-level decision about what an outcome means.
        return compute_exit_code(
            applied.checked.diagnostics_list,
            had_error=applied.checked.error or applied.outcome.write_failed,
        )
    return report_run(
        checked_files,
        discovery_inputs,
        options,
        resolved_collaborators,
    )
