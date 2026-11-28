"""Parse options for the builtin rule discovery commands.

The parser is the validation boundary for the two commands: an unknown
severity, an empty prefix, or an unsupported output format exits with status
two before any catalogue query runs. The option records it produces are
immutable and hold a domain :class:`~stilyagi.rules.catalogue.RuleFilters`, not
an argparse namespace.
"""

import argparse
import dataclasses as dc
import typing as typ

from stilyagi.rules.catalogue import RuleFilters

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_TRI_STATE: typ.Final[dict[str, bool | None]] = {
    "all": None,
    "yes": True,
    "no": False,
}
_SEVERITIES: typ.Final[tuple[str, ...]] = ("error", "warning", "info")
_OUTPUT_FORMATS: typ.Final[tuple[str, ...]] = ("text", "json")


@dc.dataclass(frozen=True, slots=True)
class RuleListOptions:
    """Options for one `stilyagi rules` invocation.

    Parameters
    ----------
    filters:
        The catalogue filter conjunction. Its defaults select every rule.
    output_format:
        ``text`` or ``json``.
    """

    filters: RuleFilters = dc.field(default_factory=RuleFilters)
    output_format: str = "text"


@dc.dataclass(frozen=True, slots=True)
class RuleDetailOptions:
    """Options for one `stilyagi rule CODE` invocation.

    Parameters
    ----------
    code:
        The complete, case-sensitive rule code.
    output_format:
        ``text`` or ``json``.
    """

    code: str
    output_format: str = "text"


def rule_options_from_args(args: argparse.Namespace) -> RuleDetailOptions:
    """Build immutable options for one rule detail command.

    Parameters
    ----------
    args:
        Parsed namespace from the `rule` subparser.

    Returns
    -------
    RuleDetailOptions
        The normalized invocation options.

    Examples
    --------
    >>> from argparse import Namespace
    >>> parsed = Namespace(code="MD001", output_format="json")
    >>> rule_options_from_args(parsed)
    RuleDetailOptions(code='MD001', output_format='json')
    """
    return RuleDetailOptions(code=args.code, output_format=args.output_format)


def rules_options_from_args(args: argparse.Namespace) -> RuleListOptions:
    """Build immutable options for one rule list command.

    Parameters
    ----------
    args:
        Parsed namespace from the `rules` subparser.

    Returns
    -------
    RuleListOptions
        The normalized invocation options, with tri-state flags converted to
        ``True``, ``False``, or ``None``.

    Examples
    --------
    >>> from argparse import Namespace
    >>> parsed = Namespace(
    ...     select="TERM",
    ...     pack=None,
    ...     severity=None,
    ...     preview="no",
    ...     fixable="all",
    ...     output_format="text",
    ... )
    >>> options = rules_options_from_args(parsed)
    >>> options.filters.prefix
    'TERM'
    >>> options.filters.preview
    False
    >>> options.filters.fixable is None
    True
    """
    return RuleListOptions(
        filters=RuleFilters(
            prefix=args.select,
            pack=args.pack,
            severity=args.severity,
            preview=_TRI_STATE[args.preview],
            fixable=_TRI_STATE[args.fixable],
        ),
        output_format=args.output_format,
    )


def add_rule_subcommands(
    add_parser: cabc.Callable[..., argparse.ArgumentParser],
    *,
    version: str,
) -> None:
    """Register the `rule` and `rules` subcommands on a parser.

    Parameters
    ----------
    add_parser:
        The parent parser's subcommand factory, usually
        ``subparsers.add_parser``.
    version:
        The already-rendered `--version` line for each subcommand.

    Examples
    --------
    >>> parser = argparse.ArgumentParser()
    >>> subparsers = parser.add_subparsers(dest="command")
    >>> add_rule_subcommands(subparsers.add_parser, version="stilyagi 0")
    >>> parser.parse_args(["rules", "--select", "MD"]).select
    'MD'
    """
    rule_parser = add_parser(
        "rule", help="Show full documentation for one builtin rule."
    )
    rule_parser.add_argument("-V", "--version", action="version", version=version)
    _add_rule_arguments(rule_parser)
    rules_parser = add_parser(
        "rules",
        help="List builtin rules without reading project configuration.",
    )
    rules_parser.add_argument("-V", "--version", action="version", version=version)
    _add_rules_arguments(rules_parser)


def _add_rule_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the one-code detail command's arguments."""
    _add_output_format_argument(parser)
    parser.add_argument(
        "code",
        metavar="CODE",
        help="Complete, case-sensitive code such as TERM001.",
    )


def _add_rules_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the list command's filter and format arguments."""
    parser.add_argument(
        "--select",
        metavar="PREFIX",
        type=_parse_nonempty,
        help="Select rules whose code starts with this case-sensitive prefix.",
    )
    parser.add_argument(
        "--pack",
        metavar="PACK",
        type=_parse_nonempty,
        help="Select rules owned by this exact pack.",
    )
    parser.add_argument(
        "--severity",
        choices=_SEVERITIES,
        metavar="{error,warning,info}",
        help="Select rules with this default severity.",
    )
    parser.add_argument(
        "--preview",
        choices=tuple(_TRI_STATE),
        default="all",
        metavar="{all,yes,no}",
        help="Select preview or non-preview rules.",
    )
    parser.add_argument(
        "--fixable",
        choices=tuple(_TRI_STATE),
        default="all",
        metavar="{all,yes,no}",
        help="Select rules that can propose actual edits.",
    )
    _add_output_format_argument(parser)


def _add_output_format_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared output-format selection."""
    parser.add_argument(
        "--output-format",
        choices=_OUTPUT_FORMATS,
        default="text",
        metavar="{text,json}",
        help="Render the catalogue as text or JSON.",
    )


def _parse_nonempty(value: str) -> str:
    """Reject an empty prefix or pack value at the parser boundary."""
    if not value:
        message = "expected a non-empty value"
        raise argparse.ArgumentTypeError(message)
    return value


__all__ = [
    "RuleDetailOptions",
    "RuleListOptions",
    "add_rule_subcommands",
    "rule_options_from_args",
    "rules_options_from_args",
]
