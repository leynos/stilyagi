"""Run the read-only builtin rule discovery commands.

Both commands answer from the static catalogue. They do not discover project
configuration, read a document, run a rule, load a plugin, or touch the
extraction cache, which is what makes them usable while a repository's
configuration is broken.

The command shell owns the failure spelling and exit status: an unknown code
is one ``stilyagi rule: ...`` line on the error stream and status two, with an
empty result stream, even when JSON output was requested.
"""

import typing as typ

from stilyagi import cli_command_shell
from stilyagi.rule_rendering import render_rule_detail, render_rule_list
from stilyagi.rules import catalogue

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from stilyagi.cli_rule_args import RuleDetailOptions, RuleListOptions

__all__ = ["run_rule_detail", "run_rule_list"]


def run_rule_list(
    options: RuleListOptions,
    *,
    output: typ.TextIO | None = None,
    error: typ.TextIO | None = None,
) -> int:
    """List the builtin rules that satisfy ``options.filters``.

    Parameters
    ----------
    options:
        Parsed filters and output format.
    output:
        Result stream, or ``None`` for standard output.
    error:
        Failure stream, or ``None`` for standard error.

    Returns
    -------
    int
        Zero on success, including an empty filtered result.

    Examples
    --------
    >>> from io import StringIO
    >>> from stilyagi.cli_rule_args import RuleListOptions
    >>> sink = StringIO()
    >>> run_rule_list(RuleListOptions(), output=sink)
    0
    >>> "MD001" in sink.getvalue()
    True
    """
    streams = cli_command_shell.command_streams(output, error)
    rules = catalogue.list_rules(options.filters)
    streams.output.write(render_rule_list(rules, options.output_format))
    return 0


def run_rule_detail(
    options: RuleDetailOptions,
    *,
    output: typ.TextIO | None = None,
    error: typ.TextIO | None = None,
) -> int:
    r"""Render the complete documentation for one exact rule code.

    Parameters
    ----------
    options:
        Parsed code and output format.
    output:
        Result stream, or ``None`` for standard output.
    error:
        Failure stream, or ``None`` for standard error.

    Returns
    -------
    int
        Zero on success, or two when no rule has the exact code.

    Examples
    --------
    >>> from io import StringIO
    >>> from stilyagi.cli_rule_args import RuleDetailOptions
    >>> result = StringIO()
    >>> failure = StringIO()
    >>> run_rule_detail(
    ...     RuleDetailOptions("UNKNOWN"), output=result, error=failure
    ... )
    2
    >>> result.getvalue()
    ''
    >>> failure.getvalue()
    'stilyagi rule: unknown rule code: UNKNOWN\n'
    """
    streams = cli_command_shell.command_streams(output, error)
    try:
        rule = catalogue.get_rule(options.code)
    except catalogue.RuleNotFoundError as exc:
        # The domain error keeps the raw code, so the one-line guarantee is
        # this adapter's responsibility rather than the catalogue's.
        escaped = cli_command_shell.escape_control_characters(exc.code)
        return cli_command_shell.write_command_failure(
            streams.error,
            command="rule",
            failure=f"unknown rule code: {escaped}",
        )
    streams.output.write(render_rule_detail(rule, options.output_format))
    return 0
