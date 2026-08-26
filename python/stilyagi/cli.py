"""Command-line interface for Stilyagi."""

import dataclasses as dc
import logging
import pathlib
import sys
import typing as typ

from stilyagi import config, diagnostics, discovery, engine, model
from stilyagi.cli_args import (
    PACKAGE_VERSION,
    PROGRAM_NAME,
    CheckOptions,
    build_parser,
    options_from_args,
)
from stilyagi.engine.checker import map_ir_errors
from stilyagi.rules import registry as rules_registry

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


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input."""

    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax
    source_text: str | None = None

    @classmethod
    def from_discovered(
        cls,
        file: discovery.DiscoveredFile,
        *,
        source_text: str | None = None,
    ) -> typ.Self:
        """Convert one discovery result into a file-backed check input."""
        return cls(
            reported_path=file.reported_path,
            resolved_path=file.resolved_path,
            syntax=file.syntax,
            source_text=source_text,
        )


type _DiscoveryInputs = tuple[tuple[CheckInput, ...], int]


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
    resolver = resolver if resolver is not None else config.ConfigResolver()
    renderer = renderer if renderer is not None else engine.RendererRegistry()
    had_error = False
    diagnostics_list: list[diagnostics.Diagnostic] = []

    _LOGGER.debug("target discovery started for %r", options.targets)
    try:
        discovery_inputs = _discover_targets(options, resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
        ValueError,
    ) as error:
        _LOGGER.warning("target discovery failed: %s", error)
        _report_check_error(None, error)
        return 2
    _LOGGER.debug("target discovery finished: %d input(s)", len(discovery_inputs[0]))

    diagnostics_list, had_error, unreadable_files = _check_discovered_files(
        discovery_inputs[0],
        options,
        resolver,
    )

    _LOGGER.debug(
        "rendering %d diagnostic(s) as %s",
        len(diagnostics_list),
        options.output_format,
    )
    summary = engine.RunSummary.from_diagnostics(
        diagnostics_list,
        checked_files=len(discovery_inputs[0]),
        skipped_files=discovery_inputs[1],
        unreadable_files=unreadable_files,
    )
    rendered = renderer.render(diagnostics_list, options.output_format, summary)
    print(rendered, end="")
    exit_code = compute_exit_code(diagnostics_list, had_error=had_error)
    _LOGGER.info("config resolver cache stats: %s", resolver.cache_stats)
    _LOGGER.debug("check complete: exit code %d", exit_code)
    return exit_code


def _check_discovered_files(
    check_inputs: cabc.Iterable[CheckInput],
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> tuple[list[diagnostics.Diagnostic], bool, int]:
    """Check every input and accumulate diagnostics and operational outcomes."""
    had_error = False
    unreadable_files = 0
    diagnostics_list: list[diagnostics.Diagnostic] = []
    for check_input in check_inputs:
        file_diagnostics, file_error, was_unreadable = _check_one_file(
            check_input, options, resolver
        )
        diagnostics_list.extend(file_diagnostics)
        had_error = had_error or file_error
        unreadable_files += int(was_unreadable)
    return diagnostics_list, had_error, unreadable_files


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
) -> _DiscoveryInputs:
    """Discover registered files beneath the requested targets."""
    resolved_targets = [pathlib.Path(target).expanduser() for target in options.targets]
    has_stdin_target = any(target.as_posix() == "-" for target in resolved_targets)
    if has_stdin_target and len(resolved_targets) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    if has_stdin_target:
        check_input = _stdin_check_input(options.stdin_filename)
        return (() if check_input is None else (check_input,), int(check_input is None))
    discovery_config = _resolve_discovery_config(options, resolver)
    result = discovery.discover_files_with_summary(
        resolved_targets,
        discovery_config,
    )
    return (
        tuple(CheckInput.from_discovered(file) for file in result.files),
        result.skipped_files,
    )


def _resolve_discovery_config(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the configuration that governs registered-source discovery.

    Discovery is a single pass over every target, so it is governed by the
    configuration resolved for the current working directory rather than by any
    individual file's nearest config. Resolving it here keeps ``--isolated``,
    explicit ``--config`` values, and CLI overrides in force during discovery.

    Returns
    -------
    config.StilyagiConfig
        The configuration used to discover registered source inputs.
    """
    return resolver.resolve_config_for_path(
        pathlib.Path(),
        cli_overrides=_build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


def _stdin_check_input(stdin_filename: str | None) -> CheckInput | None:
    """Build the check input that consumes standard input."""
    syntax = (
        model.Syntax.MARKDOWN
        if stdin_filename is None
        else discovery.syntax_for_path(pathlib.Path(stdin_filename))
    )
    if syntax is None:
        _LOGGER.warning(
            "skipping stdin without a registered extractor: %s",
            stdin_filename,
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


def _read_source(check_input: CheckInput) -> str | None:
    """Return the source text for one input, reporting read failures."""
    try:
        source = check_input.source_text
        if source is None:
            source = check_input.resolved_path.read_text(encoding="utf-8-sig")
    except (MemoryError, OSError, UnicodeDecodeError) as exc:
        _report_file_error(check_input.reported_path, exc)
        return None
    return source


def _check_one_file(
    check_input: CheckInput,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> tuple[list[diagnostics.Diagnostic], bool, bool]:
    """Check one input and report operational and read-failure outcomes."""
    source = _read_source(check_input)
    if source is None:
        return [], True, True

    _LOGGER.debug("extracting %s", check_input.reported_path)
    try:
        document = engine.extract_document(source, check_input.syntax)
    except engine.BridgeExtractionError as exc:
        _report_check_error(check_input.resolved_path, exc)
        return [], True, False
    except Exception:
        _LOGGER.exception(
            "unexpected extraction failure for %s",
            check_input.reported_path,
        )
        raise

    _LOGGER.debug("resolving config for %s", check_input.reported_path)
    try:
        resolved_config = _resolve_config(check_input.resolved_path, options, resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
    ) as exc:
        _report_check_error(check_input.resolved_path, exc)
        return [], True, False

    diagnostics_list = [
        *map_ir_errors(document, check_input.reported_path),
        *rules_registry.run_rules(document, resolved_config),
    ]
    return diagnostics_list, False, False


def _report_file_error(path: str, error: Exception) -> None:
    """Log a human-readable file read failure once."""
    message = f"{PROGRAM_NAME} check: failed to read {path}: {error}"
    _LOGGER.warning("%s", message)


def _report_check_error(path: pathlib.Path | None, error: Exception) -> None:
    """Log a human-readable extraction failure once."""
    if path is None:
        message = f"{PROGRAM_NAME} check: {error}"
    else:
        message = f"{PROGRAM_NAME} check: failed to check {path.as_posix()}: {error}"
    _LOGGER.warning("%s", message)
