"""Subprocess launchers for the canonical-IR inspection command.

`tests/test_dump_ir.py` mixes two kinds of check: in-process command-boundary
contracts and end-to-end runs of `python -m stilyagi dump-ir`. The launchers
live here so the contract module stays under the module-length ceiling, and so
the isolation choice is stated once rather than at every call site.
"""

import typing as typ

from tests.support.subprocess_env import run_python_module

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib
    import subprocess

    type CapturedProcess = subprocess.CompletedProcess[bytes]


def run_isolated_dump_ir(
    cwd: pathlib.Path,
    *arguments: str,
    stdin_bytes: bytes | None = None,
) -> CapturedProcess:
    """Run one isolated dump-ir subprocess with the checkout importable.

    The subprocess inherits the developer's real environment, so a run that
    discovers configuration can read a file from outside the temporary
    directory and report that machine's settings. Passing `--isolated` keys
    these runs on the arguments alone.

    A test that exists to observe discovery itself must not use this helper;
    `run_discovering_dump_ir` runs the same command without the flag.

    Parameters
    ----------
    cwd
        Directory the invocation runs in and resolves relative targets from.
    *arguments
        The positional targets to hand the command.
    stdin_bytes
        Bytes to pipe, or ``None`` to close standard input.

    Returns
    -------
    subprocess.CompletedProcess[bytes]
        The isolated run's status, standard output and standard error.

    Examples
    --------
    >>> from pathlib import Path
    >>> result = run_isolated_dump_ir(Path.cwd(), "--help")
    >>> result.returncode
    0
    """
    return _run_with_flags(cwd, ("--isolated",), arguments, stdin_bytes)


def run_discovering_dump_ir(
    cwd: pathlib.Path,
    *arguments: str,
    stdin_bytes: bytes | None = None,
) -> CapturedProcess:
    """Run dump-ir with discovery enabled, for tests about discovery itself."""
    return _run_with_flags(cwd, (), arguments, stdin_bytes)


def _run_with_flags(
    cwd: pathlib.Path,
    flags: cabc.Sequence[str],
    arguments: cabc.Sequence[str],
    stdin_bytes: bytes | None,
) -> CapturedProcess:
    """Run one dump-ir subprocess with `flags` before the caller's arguments."""
    return run_python_module(
        cwd,
        "dump-ir",
        *flags,
        *arguments,
        stdin_bytes=stdin_bytes,
    )
