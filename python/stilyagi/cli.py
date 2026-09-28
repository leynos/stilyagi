"""Command-line interface for Stilyagi."""

import dataclasses as dc
import logging
import pathlib
import sys
import typing as typ

from stilyagi import config, diagnostics, discovery, engine
from stilyagi.cli_args import (
    PACKAGE_VERSION,
    CheckOptions,
    build_parser,
    options_from_args,
)
from stilyagi.cli_config import resolve_discovery_config
from stilyagi.cli_io import CheckInput, report_check_error, stdin_check_input
from stilyagi.cli_pipeline import (
    CheckedFile,
    CheckReporter,
    CheckRun,
    aggregate_checked_files,
    collect_checked_files,
)
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

    options = options_from_args(args)
    _configure_logging(options)
    return run_check(options)


def _configure_logging(options: CheckOptions) -> None:
    """Apply the requested verbosity level before running the check loop."""
    if options.silent or options.quiet:
        logging.basicConfig(level=logging.WARNING)
    elif options.verbose:
        logging.basicConfig(level=logging.INFO)


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
        _LOGGER.warning("--fix and --diff cannot be combined")
        resolved_collaborators.reporter(
            None,
            ValueError(_FIX_DIFF_CONFLICT),
        )
        return 2
    _LOGGER.debug("target discovery started for %r", options.targets)
    try:
        discovered_files = _discover_targets(options, resolved_collaborators.resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
        ValueError,
    ) as error:
        _LOGGER.warning("target discovery failed: %s", error)
        resolved_collaborators.reporter(None, error)
        return 2
    _LOGGER.debug("target discovery finished: %d input(s)", len(discovered_files))

    run = CheckRun(
        options=options,
        resolver=resolved_collaborators.resolver,
        rule_runner=resolved_collaborators.rule_runner,
        report=resolved_collaborators.reporter,
    )
    checked_files = collect_checked_files(discovered_files, run)
    return _render_and_exit(checked_files, options, resolved_collaborators)


def _render_and_exit(
    checked_files: cabc.Sequence[CheckedFile],
    options: CheckOptions,
    resolved_collaborators: CheckCollaborators,
) -> int:
    """Render one run's results to the right streams and return its exit code."""
    aggregate = aggregate_checked_files(checked_files)

    _LOGGER.debug(
        "rendering %d diagnostic(s) as %s",
        len(aggregate.diagnostics_list),
        options.output_format,
    )
    rendered = resolved_collaborators.renderer.render(
        aggregate.diagnostics_list,
        options.output_format,
        fix_errors=aggregate.fix_errors,
    )
    # Under --diff the machine artefact owns stdout alone: diagnostics and the
    # summary go to stderr so `stilyagi check --diff | git apply` stays usable.
    diagnostics_output = sys.stderr if options.diff else resolved_collaborators.output
    print(rendered, end="", file=diagnostics_output)
    if options.diff:
        print("".join(aggregate.patches), end="", file=resolved_collaborators.output)
    exit_code = compute_exit_code(aggregate.diagnostics_list, had_error=aggregate.error)
    _LOGGER.debug("check complete: exit code %d", exit_code)
    return exit_code


def compute_exit_code(
    diagnostics_list: cabc.Sequence[diagnostics.Diagnostic],
    *,
    had_error: bool = False,
) -> int:
    """Return the documented exit code for one check run.

    Returns
    -------
    int
        Zero for success, one for diagnostics, or two for an operational
        error.

    Examples
    --------
    >>> compute_exit_code([])
    0
    >>> compute_exit_code([
    ...     diagnostics.Diagnostic(path="docs/example.md", code="STY001", message="x")
    ... ])
    1
    >>> compute_exit_code([], had_error=True)
    2
    """
    if had_error:
        return 2
    if diagnostics_list:
        return 1
    return 0


def _parse_targets(
    options: CheckOptions,
) -> tuple[list[pathlib.Path], bool]:
    """Split the requested targets into paths, and whether stdin was asked for.

    The ``-`` sentinel is matched against the expanded path, so ``./-`` names
    standard input just as ``-`` does.

    Returns
    -------
    tuple[list[pathlib.Path], bool]
        The expanded target paths, and whether one of them requested stdin.

    Raises
    ------
    ValueError
        Stdin was requested alongside at least one file target. Reading a
        single stream cannot also walk the filesystem, so the two are
        mutually exclusive.
    """
    resolved_targets = [pathlib.Path(target).expanduser() for target in options.targets]
    has_stdin_target = any(target.as_posix() == "-" for target in resolved_targets)
    if has_stdin_target and len(resolved_targets) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    return resolved_targets, has_stdin_target


def _discover_targets(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> list[CheckInput]:
    """Discover Markdown files beneath the requested targets."""
    resolved_targets, has_stdin_target = _parse_targets(options)
    if has_stdin_target:
        return [stdin_check_input(options.stdin_filename)]
    discovery_config = resolve_discovery_config(options, resolver)
    return [
        CheckInput(
            reported_path=discovered_file.reported_path,
            resolved_path=discovered_file.resolved_path,
        )
        for discovered_file in discovery.discover_markdown_files(
            resolved_targets,
            discovery_config,
        )
    ]
