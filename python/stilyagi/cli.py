"""Command-line interface for Stilyagi."""

from __future__ import annotations

import argparse
import dataclasses as dc
import logging
import pathlib
import sys
import typing as typ

from stilyagi import config, diagnostics, discovery, engine, model
from stilyagi.engine.checker import map_ir_errors
from stilyagi.rules import registry as rules_registry

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PACKAGE_VERSION = "0.1.0"
_OUTPUT_FORMATS = {"text", "json"}
_PROGRAM_NAME = "stilyagi"


@dc.dataclass(frozen=True, slots=True)
class CheckOptions:
    """Options for one `stilyagi check` invocation."""

    targets: tuple[str, ...]
    stdin_filename: str | None = None
    output_format: str = "text"
    explicit_config: tuple[str | pathlib.Path, ...] = ()
    isolated: bool = False
    no_cache: bool = False
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    extend_select: tuple[str, ...] = ()
    quiet: bool = False
    verbose: bool = False
    silent: bool = False


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input."""

    reported_path: str
    resolved_path: pathlib.Path
    source_text: str | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the `check` command.

    Examples
    --------
    >>> parser = build_parser()
    >>> parser.prog
    'stilyagi'
    """
    parser = argparse.ArgumentParser(prog=_PROGRAM_NAME)
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{_PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    subparsers = parser.add_subparsers(dest="command")
    check_parser = subparsers.add_parser("check", help="Check Markdown files.")
    check_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{_PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    _add_check_arguments(check_parser)
    return parser


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

    options = CheckOptions(
        targets=tuple(args.targets),
        stdin_filename=args.stdin_filename,
        output_format=args.output_format,
        explicit_config=tuple(args.config),
        isolated=args.isolated,
        no_cache=args.no_cache,
        select=tuple(code for group in args.select for code in group),
        ignore=tuple(code for group in args.ignore for code in group),
        extend_select=tuple(code for group in args.extend_select for code in group),
        quiet=args.quiet,
        verbose=args.verbose,
        silent=args.silent,
    )
    _configure_logging(options)
    return run_check(options)


def _add_check_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the `check` command arguments to one parser."""
    parser.add_argument(
        "--select",
        action="append",
        default=(),
        type=_parse_rule_codes,
        metavar="CODES",
        help="Select additional rule codes or prefixes.",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=(),
        type=_parse_rule_codes,
        metavar="CODES",
        help="Ignore rule codes or prefixes.",
    )
    parser.add_argument(
        "--extend-select",
        action="append",
        default=(),
        type=_parse_rule_codes,
        metavar="CODES",
        help="Extend the active rule selection.",
    )
    parser.add_argument(
        "--output-format",
        default="text",
        metavar="{text,json}",
        type=_parse_output_format,
        help="Render diagnostics as text or JSON.",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=(),
        metavar="VALUE",
        help="Use one explicit config file or inline TOML fragment.",
    )
    parser.add_argument(
        "--stdin-filename",
        metavar="VALUE",
        help="Report stdin diagnostics with this path instead of <stdin>.",
    )
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="Skip config discovery for the checked targets.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Accept cache disabling requests without changing behaviour yet.",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true", help="Reduce chatter.")
    verbosity.add_argument("--verbose", action="store_true", help="Increase chatter.")
    verbosity.add_argument("--silent", action="store_true", help="Suppress chatter.")
    parser.add_argument(
        "targets",
        nargs="*",
        default=("."),
        metavar="FILES",
        help="Markdown files or directories to check.",
    )


def _configure_logging(options: CheckOptions) -> None:
    """Apply the requested verbosity level before running the check loop."""
    if options.silent or options.quiet:
        logging.basicConfig(level=logging.WARNING)
    elif options.verbose:
        logging.basicConfig(level=logging.INFO)


def _parse_rule_codes(value: str) -> tuple[str, ...]:
    """Split one comma-delimited rule-code list."""
    items = tuple(code.strip() for code in value.split(",") if code.strip())
    if not items:
        message = "expected at least one rule code or prefix"
        raise argparse.ArgumentTypeError(message)
    return items


def _parse_output_format(value: str) -> str:
    """Validate the supported output formats."""
    if value in _OUTPUT_FORMATS:
        return value
    if value == "sarif":
        message = "`sarif` is planned for a later slice but is not yet available"
        raise argparse.ArgumentTypeError(message)
    message = f"invalid output format {value!r}; choose from text or json"
    raise argparse.ArgumentTypeError(message)


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
) -> config.StilyagiConfig:
    """Resolve the effective config for one target path."""
    return config.resolve_config_for_path(
        target,
        cli_overrides=_build_cli_overrides(options) or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )


def run_check(options: CheckOptions) -> int:
    """Run the check command and print rendered diagnostics."""
    had_error = False
    diagnostics_list: list[diagnostics.Diagnostic] = []

    try:
        discovered_files = _discover_targets(
            options.targets,
            options.stdin_filename,
        )
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
        ValueError,
    ) as error:
        _report_check_error(None, error)
        return 2

    for discovered_file in discovered_files:
        file_diagnostics, file_error = _check_one_file(discovered_file, options)
        diagnostics_list.extend(file_diagnostics)
        had_error = had_error or file_error
        if had_error:
            break

    if had_error:
        return 2

    rendered = engine.RendererRegistry().render(
        diagnostics_list,
        options.output_format,
    )
    print(rendered, end="")
    return compute_exit_code(diagnostics_list)


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
    targets: cabc.Iterable[str],
    stdin_filename: str | None,
) -> list[CheckInput]:
    """Discover Markdown files beneath the requested targets."""
    resolved_targets = [pathlib.Path(target).expanduser() for target in targets]
    has_stdin_target = any(target.as_posix() == "-" for target in resolved_targets)
    if has_stdin_target and len(resolved_targets) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    if has_stdin_target:
        reported_path = (
            pathlib.Path(stdin_filename).as_posix() if stdin_filename else "<stdin>"
        )
        resolved_path = (
            pathlib.Path(stdin_filename) if stdin_filename else pathlib.Path("<stdin>")
        )
        return [
            CheckInput(
                reported_path=reported_path,
                resolved_path=resolved_path,
                source_text=sys.stdin.read(),
            ),
        ]
    return [
        CheckInput(
            reported_path=discovered_file.reported_path,
            resolved_path=discovered_file.resolved_path,
        )
        for discovered_file in discovery.discover_markdown_files(
            resolved_targets,
            config.StilyagiConfig(),
        )
    ]


def _check_one_file(
    check_input: CheckInput,
    options: CheckOptions,
) -> tuple[list[diagnostics.Diagnostic], bool]:
    """Check one discovered Markdown file or stdin payload."""
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
        return [], True

    try:
        document = engine.extract_document(source, model.Syntax.MARKDOWN)
    except Exception as exc:  # noqa: BLE001 - the bridge maps internal failures here.
        _report_check_error(check_input.resolved_path, exc)
        return [], True

    try:
        resolved_config = _resolve_config(check_input.resolved_path, options)
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
    print(f"{_PROGRAM_NAME} check: {message}", file=sys.stderr)


def _report_check_error(path: pathlib.Path | None, error: Exception) -> None:
    """Print a human-readable extraction failure."""
    if path is None:
        message = str(error)
    else:
        message = f"failed to check {path.as_posix()}: {error}"
    print(f"{_PROGRAM_NAME} check: {message}", file=sys.stderr)
