"""Resolve a `check` invocation's targets into the inputs to be checked.

The `check` command accepts two shapes of target, and they are mutually
exclusive. The `-` sentinel names standard input, whose bytes never touch the
filesystem; anything else names a path, which is expanded and walked for
registered sources. Deciding which shape was asked for, and building the
resulting inputs, is one cohesive job that the command module does not need to
carry: `cli.py` binds the sequence of stages, and this module answers the
single question that opens it.

The dependency direction stays inward. This module imports `cli_config`,
`cli_io` and `discovery`; none of them imports it back, so the command remains
the only module that knows the order the stages run in.
"""

import pathlib
import typing as typ

from stilyagi import config, discovery, model
from stilyagi.check_inputs import (
    CheckInput,
    DiscoveryInputs,
)
from stilyagi.cli_config import resolve_discovery_config
from stilyagi.cli_io import report_check_error, stdin_check_input
from stilyagi.discovery_results import SkippedCandidateCount

if typ.TYPE_CHECKING:
    from stilyagi.cli_args import CheckOptions

__all__ = [
    "discover_targets",
    "parse_targets",
]


def parse_targets(options: CheckOptions) -> tuple[list[pathlib.Path], bool]:
    """Split the requested targets into paths, and whether stdin was asked for.

    The ``-`` sentinel is matched against the normalized path, so ``./-`` names
    standard input just as ``-`` does: `Path` drops the redundant ``./``
    prefix, and the comparison reads the result.

    Expansion is deliberately *not* performed here. `Path.expanduser` consults
    the environment for the home directory, and it raises `RuntimeError` when
    that lookup fails -- for example when ``HOME`` is unset. Doing it in this
    function would put a fallible filesystem-adjacent call in the one place
    with no error channel: the command binds this stage in a plain `try` whose
    handler distinguishes operational failures by type, and an unguarded
    `RuntimeError` would escape the CLI entirely rather than becoming the exit-2
    status an unresolvable target deserves. Discovery already expands each
    target and already catches exactly that failure, so the expansion lives
    there, beside the guard that gives it a meaning.

    Parameters
    ----------
    options:
        The parsed options for one `check` invocation.

    Returns
    -------
    tuple[list[pathlib.Path], bool]
        The requested target paths as normalized `Path` objects, and whether
        one of them requested stdin.

    Raises
    ------
    ValueError
        Stdin was requested alongside at least one file target. Reading a
        single stream cannot also walk the filesystem, so the two are
        mutually exclusive.

    Examples
    --------
    >>> from stilyagi.cli_args import CheckOptions
    >>> paths, is_stdin = parse_targets(CheckOptions(targets=("docs",)))
    >>> [path.as_posix() for path in paths]
    ['docs']
    >>> is_stdin
    False
    >>> parse_targets(CheckOptions(targets=("./-",)))[1]
    True
    >>> parse_targets(CheckOptions(targets=("-", "docs")))
    Traceback (most recent call last):
        ...
    ValueError: stdin target cannot be combined with file targets
    """
    resolved_targets = [pathlib.Path(target) for target in options.targets]
    has_stdin_target = any(target.as_posix() == "-" for target in resolved_targets)
    if has_stdin_target and len(resolved_targets) > 1:
        message = "stdin target cannot be combined with file targets"
        raise ValueError(message)
    return resolved_targets, has_stdin_target


def discover_targets(
    options: CheckOptions,
    resolver: config.ConfigResolver,
) -> DiscoveryInputs:
    """Discover registered files beneath the requested targets.

    When stdin was requested the filesystem is not touched at all: the stream
    becomes the single input, or a skipped candidate once ``--stdin-filename``
    names a suffix with no registered extractor.

    Parameters
    ----------
    options:
        The parsed options for one `check` invocation.
    resolver:
        The configuration resolver discovery uses to find the effective
        discovery settings.

    Returns
    -------
    DiscoveryInputs
        The inputs to check, the count of skipped candidates, and any
        structured notices, failures or per-reason skip counts.
    """
    target_paths, has_stdin_target = parse_targets(options)
    if has_stdin_target:
        check_input = _stdin_check_input(options.stdin_filename)
        return DiscoveryInputs(
            inputs=() if check_input is None else (check_input,),
            skipped_files=int(check_input is None),
            skipped_by_reason=(
                (SkippedCandidateCount("unregistered_candidate", 1),)
                if check_input is None
                else ()
            ),
        )
    discovery_config = resolve_discovery_config(options, resolver)
    result = discovery.discover_files_with_summary(
        target_paths,
        discovery_config,
    )
    return DiscoveryInputs(
        inputs=tuple(CheckInput.from_discovered(file) for file in result.files),
        skipped_files=result.skipped_files,
        notices=result.notices,
        failures=result.failures,
        skipped_by_reason=result.skipped_by_reason,
    )


def _stdin_check_input(stdin_filename: str | None) -> CheckInput | None:
    """Build the check input that consumes standard input.

    The stream's syntax is chosen here, because only the command knows that a
    missing ``--stdin-filename`` means Markdown. The record itself is built by
    `cli_io.stdin_check_input`, which owns the read boundary: it reads the
    piped bytes without newline translation and flags them ``from_stdin``. That
    flag is what stops a later `--fix` stage from resolving the reported name
    and overwriting a real file, so the read must not be reimplemented here
    (D-05).

    Returns
    -------
    CheckInput | None
        The stream input, or ``None`` once an unsupported ``--stdin-filename``
        has been reported as a skipped candidate.
    """
    syntax = (
        model.Syntax.MARKDOWN
        if stdin_filename is None
        else discovery.syntax_for_path(pathlib.Path(stdin_filename))
    )
    if syntax is None:
        report_check_error(
            None,
            ValueError(
                f"skipping stdin without a registered extractor: {stdin_filename}"
            ),
        )
        return None
    return stdin_check_input(stdin_filename, syntax)
