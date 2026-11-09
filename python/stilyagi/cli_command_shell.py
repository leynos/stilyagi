"""State the report shape every command's expected failure shares.

A command that fails for an expected operational reason -- a missing target, an
unreadable file, a configuration that cannot be resolved -- reports it the same
way: one `stilyagi <command>: <reason>` line on the error stream, then status
two. `write_command_failure` renders that sentence and chooses that status;
`command_streams` resolves the optional output and error streams every command
accepts, so no command has to name a `None` fallback itself.

Both live here rather than in `cli_io` because they are policy, not byte
handling, and because stating them once is what keeps configuration
inspection, `dump-ir`, and `clean` failing alike instead of three command
shells drifting apart. A new command should import this module rather than
render its own prefix or pick its own exit code.

The module holds no state and chooses nothing about *which* failures are
expected. A command decides that by catching its own typed errors and handing
them here; this module only decides how one is spelled.
"""

import dataclasses as dc
import sys
import typing as typ

from stilyagi.cli_args import PROGRAM_NAME

__all__ = [
    "CommandStreams",
    "command_streams",
    "write_command_failure",
]


@dc.dataclass(frozen=True, slots=True)
class CommandStreams[OutputStreamT: typ.TextIO | typ.BinaryIO]:
    """The result and failure streams one command invocation reports through.

    The result stream's type is the caller's own: `dump-ir` writes bytes, so it
    receives a possibly-binary stream, while the text-only commands receive a
    `TextIO` and can write rendered text without a cast. Only the failure
    stream is fixed, because every command reports it as one line of text.

    Attributes
    ----------
    output:
        Where the command writes its result: standard output unless the
        caller supplied something else.
    error:
        Where the command writes expected failures: standard error unless the
        caller supplied something else.
    """

    output: OutputStreamT
    error: typ.TextIO


def command_streams[OutputStreamT: typ.TextIO | typ.BinaryIO](
    output: OutputStreamT | None = None,
    error: typ.TextIO | None = None,
) -> CommandStreams[OutputStreamT]:
    """Resolve one invocation's streams, defaulting each to the process's own.

    Every command accepts optional streams so tests and embedding callers can
    capture its result and its failures separately. Resolving the fallbacks
    here means each command names its two stream parameters and nothing else,
    and a caller can see from the one call site that neither is left as an
    unresolved optional.

    Parameters
    ----------
    output:
        The caller's result stream, or ``None`` for standard output.
    error:
        The caller's failure stream, or ``None`` for standard error.

    Returns
    -------
    CommandStreams
        Both streams, each resolved to a concrete object.

    Examples
    --------
    >>> import io
    >>> sink = io.StringIO()
    >>> streams = command_streams(sink)
    >>> streams.output is sink
    True
    >>> streams.error is sys.stderr
    True
    """
    return CommandStreams(
        output=typ.cast("OutputStreamT", sys.stdout) if output is None else output,
        error=sys.stderr if error is None else error,
    )


def write_command_failure(
    error: typ.TextIO,
    *,
    command: str,
    failure: object,
) -> int:
    r"""Report one operational failure in its command-prefixed form.

    Every command reports an expected operational failure as one line naming
    the subcommand and the reason, then exits two. Keeping the sentence and
    the status together here means a new command cannot quietly pick a
    different prefix, a different stream, or a different code.

    Parameters
    ----------
    error:
        The stream the failure is reported on.
    command:
        The subcommand name, which prefixes the sentence. It is the name the
        user typed rather than a module or function name.
    failure:
        The reason, rendered with `str`. A typed error carries its own
        human-readable message, so no message table is duplicated here.

    Returns
    -------
    int
        Always two, the operational-failure status, so a caller can return it
        directly.

    Examples
    --------
    >>> import io
    >>> sink = io.StringIO()
    >>> write_command_failure(sink, command="clean", failure=OSError("denied"))
    2
    >>> sink.getvalue()
    'stilyagi clean: denied\n'
    """
    error.write(f"{PROGRAM_NAME} {command}: {failure}\n")
    return 2
