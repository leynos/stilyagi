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


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input."""

    reported_path: str
    resolved_path: pathlib.Path
    source_text: str | None = None


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the Stilyagi command-line interface.

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
        Configuration resolver to reuse across every checked file. A fresh
        single-use resolver is created when one is not supplied, so no
        configuration cache is shared between invocations.
    renderer:
        Renderer used to serialise diagnostics. Defaults to a new
        :class:`~stilyagi.engine.RendererRegistry`.
    """
    resolver = resolver if resolver is not None else config.ConfigResolver()
    renderer = renderer if renderer is not None else engine.RendererRegistry()
    had_error = False
    diagnostics_list: list[diagnostics.Diagnostic] = []

    try:
        discovered_files = _discover_targets(options, resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
        ValueError,
    ) as error:
        _report_check_error(None, error)
        return 2

    for discovered_file in discovered_files:
        file_diagnostics, file_error = _check_one_file(
            discovered_file, options, resolver
        )
        diagnostics_list.extend(file_diagnostics)
        had_error = had_error or file_error

    rendered = renderer.render(diagnostics_list, options.output_format)
    print(rendered, end="")
    return compute_exit_code(diagnostics_list, had_error=had_error)


def compute_exit_code(
    diagnostics_list: cabc.Sequence[diagnostics.Diagnostic],
    *,
    had_error: bool = False,
) -> int:
    """Return the documented exit code for one check run.

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


def _discover_targets(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> list[CheckInput]:
    """Discover Markdown files beneath the requested targets."""
    resolved_targets = [pathlib.Path(target).expanduser() for target in options.targets]
    has_stdin_target = any(target.as_posix() == "-" for target in resolved_targets)
    if has_stdin_target and len(resolved_targets) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    if has_stdin_target:
        return [_stdin_check_input(options.stdin_filename)]
    discovery_config = _resolve_discovery_config(options, resolver)
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


def _resolve_discovery_config(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> config.StilyagiConfig:
    """Resolve the configuration that governs Markdown discovery.

    Discovery is a single pass over every target, so it is governed by the
    configuration resolved for the current working directory rather than by any
    individual file's nearest config. Resolving it here keeps ``--isolated``,
    explicit ``--config`` values, and CLI overrides in force during discovery.
    """
    return resolver.resolve_config_for_path(
        pathlib.Path(),
        cli_overrides=_build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


def _stdin_check_input(stdin_filename: str | None) -> CheckInput:
    """Build the check input that consumes standard input."""
    reported_path = (
        pathlib.Path(stdin_filename).as_posix() if stdin_filename else "<stdin>"
    )
    resolved_path = (
        pathlib.Path(stdin_filename) if stdin_filename else pathlib.Path("<stdin>")
    )
    return CheckInput(
        reported_path=reported_path,
        resolved_path=resolved_path,
        source_text=sys.stdin.read(),
    )


def _read_source(check_input: CheckInput) -> str | None:
    """Return the source text for one input, reporting read failures."""
    try:
        source = check_input.source_text
        if source is None:
            source = check_input.resolved_path.read_text(encoding="utf-8")
    except (
        FileNotFoundError,
        IsADirectoryError,
        PermissionError,
        UnicodeDecodeError,
    ) as exc:
        _report_file_error(check_input.resolved_path, exc)
        return None
    return source


def _check_one_file(
    check_input: CheckInput,
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> tuple[list[diagnostics.Diagnostic], bool]:
    """Check one discovered Markdown file or stdin payload."""
    source = _read_source(check_input)
    if source is None:
        return [], True

    try:
        document = engine.extract_document(source, model.Syntax.MARKDOWN)
    except Exception as exc:  # noqa: BLE001 - the bridge maps internal failures here.
        _report_check_error(check_input.resolved_path, exc)
        return [], True

    try:
        resolved_config = _resolve_config(check_input.resolved_path, options, resolver)
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
    ) as exc:
        _report_check_error(check_input.resolved_path, exc)
        return [], True

    diagnostics_list = [
        *map_ir_errors(document, check_input.reported_path),
        *rules_registry.run_rules(document, resolved_config),
    ]
    return diagnostics_list, False


def _report_file_error(path: pathlib.Path, error: Exception) -> None:
    """Print a human-readable file read failure."""
    message = f"failed to read {path.as_posix()}: {error}"
    print(f"{PROGRAM_NAME} check: {message}", file=sys.stderr)


def _report_check_error(path: pathlib.Path | None, error: Exception) -> None:
    """Print a human-readable extraction failure."""
    if path is None:
        message = str(error)
    else:
        message = f"failed to check {path.as_posix()}: {error}"
    print(f"{PROGRAM_NAME} check: {message}", file=sys.stderr)
