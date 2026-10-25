"""Parse options for the read-only canonical Markdown IR command."""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import argparse
    import collections.abc as cabc
    import pathlib


@dc.dataclass(frozen=True, slots=True)
class DumpIrOptions:
    """Options for one read-only `stilyagi dump-ir` invocation."""

    targets: tuple[str, ...]
    stdin_filename: str | None = None
    output_format: str = "json"
    explicit_config: tuple[str | pathlib.Path, ...] = ()
    isolated: bool = False
    no_cache: bool = False


def dump_ir_options_from_args(args: argparse.Namespace) -> DumpIrOptions:
    """Build immutable options for one canonical Markdown IR inspection.

    Parameters
    ----------
    args:
        Parsed namespace from the `dump-ir` subparser.

    Returns
    -------
    DumpIrOptions
        The normalized invocation options, with omitted targets expanded to
        the current directory.

    Examples
    --------
    >>> from argparse import Namespace
    >>> parsed = Namespace(
    ...     targets=[], stdin_filename=None, output_format="json",
    ...     config=[], isolated=False, no_cache=False
    ... )
    >>> dump_ir_options_from_args(parsed).targets
    ('.',)
    """
    return DumpIrOptions(
        targets=tuple(args.targets) or (".",),
        stdin_filename=args.stdin_filename,
        output_format=args.output_format,
        explicit_config=tuple(args.config),
        isolated=args.isolated,
        no_cache=args.no_cache,
    )


def _add_dump_ir_arguments(
    parser: argparse.ArgumentParser,
    *,
    add_config_argument: cabc.Callable[[argparse.ArgumentParser], None],
    add_isolated_argument: cabc.Callable[[argparse.ArgumentParser], None],
) -> None:
    """Add read-only canonical-IR options without check or rule controls."""
    parser.add_argument(
        "--output-format",
        choices=("json",),
        default="json",
        metavar="{json}",
        help="Emit canonical JSON IR.",
    )
    parser.add_argument(
        "--stdin-filename",
        metavar="VALUE",
        help="Required Markdown reporting path when reading standard input.",
    )
    add_config_argument(parser)
    add_isolated_argument(parser)
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass persistent extraction cache reads and writes.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=(".",),
        metavar="FILES",
        help="Markdown files or directories to inspect.",
    )
