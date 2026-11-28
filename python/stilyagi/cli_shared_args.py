"""Shared argparse builders for options more than one command accepts.

`--config`, `--isolated`, `--output-format`, and the repeatable rule-code
selectors mean the same thing wherever they appear. Keeping one builder per
shape means a command cannot quietly choose a different default, metavar, or
validation rule for an option the CLI contract documents once.
"""

import argparse
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_OUTPUT_FORMATS = {"text", "json"}


def flatten_rule_codes(
    groups: cabc.Iterable[tuple[str, ...]],
) -> tuple[str, ...]:
    """Flatten repeated comma-delimited rule-code arguments."""
    return tuple(code for group in groups for code in group)


def add_rule_code_argument(
    parser: argparse.ArgumentParser,
    name: str,
    help_text: str,
) -> None:
    """Add one repeatable, comma-delimited rule-code selection argument.

    ``default`` is a list rather than the empty tuple these codes are stored
    as. argparse's ``append`` action copies the default and then appends to the
    copy, and copying a tuple still yields a tuple, so a tuple default raises
    ``AttributeError`` the first time the flag is actually used.
    :func:`flatten_rule_codes` normalizes the collected list back to a tuple.
    """
    parser.add_argument(
        name,
        action="append",
        default=[],
        type=_parse_rule_codes,
        metavar="CODES",
        help=help_text,
    )


def add_output_format_argument(
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


def add_isolated_argument(
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


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Add one repeatable config path or inline TOML argument."""
    parser.add_argument(
        "--config",
        action="append",
        # A list, for the reason `add_rule_code_argument` documents: `append`
        # copies the default and appends to the copy, so a tuple default raises
        # `AttributeError: 'tuple' object has no attribute 'append'` the first
        # time the flag is used. The parsed list is normalized to a tuple by
        # each command's option builder.
        default=[],
        metavar="VALUE",
        help="Use one explicit config file or inline TOML fragment.",
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


__all__ = [
    "add_config_argument",
    "add_isolated_argument",
    "add_output_format_argument",
    "add_rule_code_argument",
    "flatten_rule_codes",
]
