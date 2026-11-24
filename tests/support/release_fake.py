"""The entry point every stand-in release tool re-executes.

A fake ``gh`` or ``curl`` is a one-line ``/bin/sh`` script that runs this
module under the interpreter pytest itself is running, so the program serving
a step does not depend on whichever ``python3`` the caller's ``PATH`` happens
to resolve. This module is what that script invokes, and all it does is record
the invocation and hand it to the stand-in for the named tool.

Three modules make up the stand-ins, split so each holds one concern:

``release_clients``
    ``gh release`` and ``curl``, plus the journal and the state directories.
``release_attestations``
    ``gh attestation``, whose policy flags and record shape are a subject in
    their own right.
``release_fake``
    This module, the only place the three are wired together.

All three are standard-library only, and this module is the only one loaded by
a fake invocation. Importing pytest or a support helper here would cost every
such invocation the test session's import graph.
"""

import sys
import typing as typ

from tests.support import release_attestations, release_clients

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _route(tool: str, args: cabc.Sequence[str]) -> int:
    """Serve one invocation of `tool` with the argument vector `args`."""
    if tool == "curl":
        return release_clients.curl(args)
    if args[:1] == ["attestation"]:
        return _attestation(args[1:])
    return release_clients.gh(args)


def _attestation(args: cabc.Sequence[str]) -> int:
    """Serve the ``gh attestation`` subcommands the workflow calls."""
    command = args[0] if args else ""
    if command == "verify":
        return release_attestations.verify(args[1:])
    print(f"the fake serves no attestation {command!r}", file=sys.stderr)
    return 1


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Journal one invocation and dispatch it to the named stand-in.

    Parameters
    ----------
    argv
        The argument vector as the program received it, the tool's own name
        first. Defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        The exit status the real command would have.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    tool, rest = args[0], args[1:]
    release_clients.journal(args)
    return _route(tool, rest)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
