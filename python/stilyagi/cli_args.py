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
from stilyagi.cli_rule_args import add_rule_subcommands
from stilyagi.cli_shared_args import (
    add_config_argument,
    add_isolated_argument,
    add_output_format_argument,
    add_rule_code_argument,
    flatten_rule_codes,
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
        `config`, `dump-ir`, `clean`, `rule`, and `rules` subcommands with
        their supported options.

    Examples
    --------
    >>> parser = build_parser()
    >>> parser.prog
    'stilyagi'
    """
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME)
    _add_version_argument(parser)
    subparsers = parser.add_subparsers(dest="command")
    _add_subcommand(
        subparsers.add_parser,
        "check",
        help_text="Check Markdown, Python, and Rust source files.",
        add_arguments=_add_check_arguments,
    )
    _add_subcommand(
        subparsers.add_parser,
        "config",
        help_text="Inspect the effective configuration without linting files.",
        add_arguments=_add_config_inspection_arguments,
    )
    _add_subcommand(
        subparsers.add_parser,
        "dump-ir",
        help_text="Emit canonical JSON IR for Markdown files.",
        add_arguments=partial(
            _add_dump_ir_arguments,
            add_config_argument=add_config_argument,
            add_isolated_argument=partial(
                add_isolated_argument,
                help_text=("Skip config discovery for the requested Markdown targets."),
            ),
        ),
    )
    subparsers.add_parser(
        "clean",
        help="Remove recognized Stilyagi caches beneath the current directory.",
    )
    add_rule_subcommands(
        subparsers.add_parser,
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )
    return parser


def _add_subcommand(
    add_parser: cabc.Callable[..., argparse.ArgumentParser],
    name: str,
    *,
    help_text: str,
    add_arguments: cabc.Callable[[argparse.ArgumentParser], None],
) -> argparse.ArgumentParser:
    """Register one subcommand with its version flag and own arguments."""
    subparser = add_parser(name, help=help_text)
    _add_version_argument(subparser)
    add_arguments(subparser)
    return subparser


def _add_version_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared `-V`/`--version` action to one parser."""
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {PACKAGE_VERSION}",
    )


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
        select=flatten_rule_codes(args.select),
        ignore=flatten_rule_codes(args.ignore),
        extend_select=flatten_rule_codes(args.extend_select),
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
        select=flatten_rule_codes(args.select),
        ignore=flatten_rule_codes(args.ignore),
        extend_select=flatten_rule_codes(args.extend_select),
    )


def _add_check_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the `check` command arguments to one parser."""
    # The three selection flags are one argument shape repeated, so they share
    # a builder; the parse result is what differs, and that is argparse's.
    add_rule_code_argument(
        parser, "--select", "Select additional rule codes or prefixes."
    )
    add_rule_code_argument(parser, "--ignore", "Ignore rule codes or prefixes.")
    add_rule_code_argument(
        parser, "--extend-select", "Extend the active rule selection."
    )
    add_output_format_argument(parser, help_text="Render diagnostics as text or JSON.")
    add_config_argument(parser)
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
    add_isolated_argument(
        parser, help_text="Skip config discovery for the checked targets."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass persistent extraction cache reads and writes.",
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
    add_output_format_argument(
        parser, help_text="Render effective values and origins as text or JSON."
    )
    add_config_argument(parser)
    add_isolated_argument(
        parser, help_text="Skip nearest-config discovery for the target."
    )
    add_rule_code_argument(
        parser, "--select", "Select additional rule codes or prefixes."
    )
    add_rule_code_argument(parser, "--ignore", "Ignore rule codes or prefixes.")
    add_rule_code_argument(
        parser, "--extend-select", "Extend the active rule selection."
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
