"""Argument parsing for Stilyagi's check and read-only CLI commands.

This module owns command parsers, option validation, and translation from
parsed arguments into immutable command-specific option values.

Example
-------
>>> parser = build_parser()
>>> parser.prog
'stilyagi'
"""

import argparse
import dataclasses as dc
import typing as typ
from functools import partial
from importlib import metadata

from stilyagi.cli_dump_ir_args import (
    DumpIrOptions as DumpIrOptions,
)
from stilyagi.cli_dump_ir_args import (
    _add_dump_ir_arguments,
)
from stilyagi.cli_dump_ir_args import (
    dump_ir_options_from_args as dump_ir_options_from_args,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

PROGRAM_NAME = "stilyagi"


def _resolve_package_version() -> str:
    """Return the installed distribution version for the CLI.

    Reading the version from installed package metadata keeps ``--version`` in
    step with the version declared in ``pyproject.toml`` instead of drifting
    from a hardcoded literal.

    Returns
    -------
    str
        The installed distribution version, or a sentinel when running from an
        uninstalled source checkout where no metadata is available.
    """
    try:
        return metadata.version(PROGRAM_NAME)
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "0+unknown"


PACKAGE_VERSION = _resolve_package_version()
_OUTPUT_FORMATS = {"text", "json"}


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
    diff: bool = False
    fix: bool = False
    unsafe_fixes: bool = False
    quiet: bool = False
    verbose: bool = False
    silent: bool = False


@dc.dataclass(frozen=True, slots=True)
class _ConfigInspectionOptions:
    """Options for one read-only `stilyagi config` invocation."""

    key: str | None
    target: str
    output_format: str
    explicit_config: tuple[str | pathlib.Path, ...]
    isolated: bool
    select: tuple[str, ...]
    ignore: tuple[str, ...]
    extend_select: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for check and read-only inspection commands.

    Returns
    -------
    argparse.ArgumentParser
        A parser exposing the top-level `--version` flag and the `check`,
        `config`, and `dump-ir` subcommands with their supported options.

    Examples
    --------
    >>> parser = build_parser()
    >>> parser.prog
    'stilyagi'
    """
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME)
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    subparsers = parser.add_subparsers(dest="command")
    check_parser = subparsers.add_parser(
        "check",
        help="Check Markdown, Python, and Rust source files.",
    )
    check_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    _add_check_arguments(check_parser)
    config_parser = subparsers.add_parser(
        "config",
        help="Inspect the effective configuration without linting files.",
    )
    config_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    _add_config_inspection_arguments(config_parser)
    dump_ir_parser = subparsers.add_parser(
        "dump-ir",
        help="Emit canonical JSON IR for Markdown files.",
    )
    dump_ir_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    _add_dump_ir_arguments(
        dump_ir_parser,
        add_config_argument=_add_config_argument,
        add_isolated_argument=partial(
            _add_isolated_argument,
            help_text="Skip config discovery for the requested Markdown targets.",
        ),
    )
    return parser


def options_from_args(args: argparse.Namespace) -> CheckOptions:
    """Build one `CheckOptions` from parsed command-line arguments.

    Parameters
    ----------
    args:
        The namespace produced by :func:`build_parser` after parsing one
        `check` invocation.

    Returns
    -------
    CheckOptions
        The immutable options object consumed by the check command, with
        repeated comma-delimited rule-code flags flattened into single tuples.
    """
    return CheckOptions(
        targets=tuple(args.targets),
        stdin_filename=args.stdin_filename,
        output_format=args.output_format,
        explicit_config=tuple(args.config),
        isolated=args.isolated,
        no_cache=args.no_cache,
        select=_flatten_rule_codes(args.select),
        ignore=_flatten_rule_codes(args.ignore),
        extend_select=_flatten_rule_codes(args.extend_select),
        diff=args.diff,
        fix=args.fix,
        unsafe_fixes=args.unsafe_fixes,
        quiet=args.quiet,
        verbose=args.verbose,
        silent=args.silent,
    )


def _config_inspection_options_from_args(
    args: argparse.Namespace,
) -> _ConfigInspectionOptions:
    """Build the immutable options for one config inspection command."""
    return _ConfigInspectionOptions(
        key=args.key,
        target=args.target,
        output_format=args.output_format,
        explicit_config=tuple(args.config),
        isolated=args.isolated,
        select=_flatten_rule_codes(args.select),
        ignore=_flatten_rule_codes(args.ignore),
        extend_select=_flatten_rule_codes(args.extend_select),
    )


def _flatten_rule_codes(
    groups: cabc.Iterable[tuple[str, ...]],
) -> tuple[str, ...]:
    """Flatten repeated comma-delimited rule-code arguments."""
    return tuple(code for group in groups for code in group)


def _add_rule_code_argument(
    parser: argparse.ArgumentParser,
    name: str,
    help_text: str,
) -> None:
    """Add one repeatable, comma-delimited rule-code selection argument.

    ``default`` is a list rather than the empty tuple these codes are stored
    as. argparse's ``append`` action copies the default and then appends to the
    copy, and copying a tuple still yields a tuple, so a tuple default raises
    ``AttributeError`` the first time the flag is actually used.
    `_flatten_rule_codes` normalises the collected list back to a tuple.
    """
    parser.add_argument(
        name,
        action="append",
        default=[],
        type=_parse_rule_codes,
        metavar="CODES",
        help=help_text,
    )


def _add_check_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the `check` command arguments to one parser."""
    # The three selection flags are one argument shape repeated, so they share
    # a builder; the parse result is what differs, and that is argparse's.
    _add_rule_code_argument(
        parser, "--select", "Select additional rule codes or prefixes."
    )
    _add_rule_code_argument(parser, "--ignore", "Ignore rule codes or prefixes.")
    _add_rule_code_argument(
        parser, "--extend-select", "Extend the active rule selection."
    )
    _add_output_format_argument(parser, help_text="Render diagnostics as text or JSON.")
    _add_config_argument(parser)
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print safe fix previews as unified diffs without changing files.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply safe fixes to the files on disk.",
    )
    parser.add_argument(
        "--unsafe-fixes",
        action="store_true",
        help="Include fixes a rule marked unsafe. Requires --fix to take effect.",
    )
    parser.add_argument(
        "--stdin-filename",
        metavar="VALUE",
        help="Report stdin diagnostics with this path instead of <stdin>.",
    )
    _add_isolated_argument(
        parser, help_text="Skip config discovery for the checked targets."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Accept cache disabling requests without changing behaviour yet.",
    )
    _add_verbosity_arguments(parser)
    _add_target_arguments(parser)


def _add_config_inspection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the read-only configuration inspection options."""
    parser.add_argument(
        "key",
        nargs="?",
        help="Show one dotted TOML key instead of the complete configuration.",
    )
    parser.add_argument(
        "--target",
        default=".",
        metavar="PATH",
        help="Inspect configuration for one existing file or directory.",
    )
    _add_output_format_argument(
        parser, help_text="Render effective values and origins as text or JSON."
    )
    _add_config_argument(parser)
    _add_isolated_argument(
        parser, help_text="Skip nearest-config discovery for the target."
    )
    _add_rule_code_argument(
        parser, "--select", "Select additional rule codes or prefixes."
    )
    _add_rule_code_argument(parser, "--ignore", "Ignore rule codes or prefixes.")
    _add_rule_code_argument(
        parser, "--extend-select", "Extend the active rule selection."
    )


def _add_output_format_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    """Add the shared JSON-or-text output option."""
    parser.add_argument(
        "--output-format",
        default="text",
        metavar="{text,json}",
        type=_parse_output_format,
        help=help_text,
    )


def _add_isolated_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    """Add the shared config-discovery bypass option."""
    parser.add_argument(
        "--isolated",
        action="store_true",
        help=help_text,
    )


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Add one repeatable config path or inline TOML argument."""
    parser.add_argument(
        "--config",
        action="append",
        # argparse copies an append default before adding values, so this must
        # remain a list; option converters normalise it to a tuple afterward.
        default=[],
        metavar="VALUE",
        help="Use one explicit config file or inline TOML fragment.",
    )


def _add_verbosity_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the mutually exclusive chatter-level flags to one parser."""
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true", help="Reduce chatter.")
    verbosity.add_argument("--verbose", action="store_true", help="Increase chatter.")
    verbosity.add_argument("--silent", action="store_true", help="Suppress chatter.")


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the trailing target operands to one parser."""
    parser.add_argument(
        "targets",
        nargs="*",
        default=(".",),
        metavar="FILES",
        help="Files or directories to check for registered prose sources.",
    )


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
