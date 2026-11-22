"""Shared invocation helpers for the builtin rule command tests.

Both the command-behaviour module and the snapshot module drive the same two
adapters with injected streams. One helper per command keeps the two modules
calling the documented boundary identically, and a change to the stream
contract is made once.
"""

import io

from stilyagi import rule_commands
from stilyagi.cli_rule_args import RuleDetailOptions, RuleListOptions
from stilyagi.rules.catalogue import RuleFilters

type CommandResult = tuple[int, str, str]
"""Status, standard output, and standard error of one in-process invocation."""


def list_result(
    *,
    filters: RuleFilters | None = None,
    output_format: str = "text",
) -> CommandResult:
    """Run the list command with the supplied filters and format.

    Parameters
    ----------
    filters:
        The catalogue filter conjunction, or ``None`` for the complete list.
    output_format:
        ``text`` or ``json``.

    Returns
    -------
    CommandResult
        The status, result stream, and failure stream.
    """
    output, error = io.StringIO(), io.StringIO()
    status = rule_commands.run_rule_list(
        RuleListOptions(
            filters=filters if filters is not None else RuleFilters(),
            output_format=output_format,
        ),
        output=output,
        error=error,
    )
    return status, output.getvalue(), error.getvalue()


def detail_result(code: str, output_format: str = "text") -> CommandResult:
    """Run the detail command for one code with the supplied format.

    Returns
    -------
    CommandResult
        The status, result stream, and failure stream.
    """
    output, error = io.StringIO(), io.StringIO()
    status = rule_commands.run_rule_detail(
        RuleDetailOptions(code=code, output_format=output_format),
        output=output,
        error=error,
    )
    return status, output.getvalue(), error.getvalue()


__all__ = ["CommandResult", "detail_result", "list_result"]
