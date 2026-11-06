"""Resolve the glob anchor for one checked file at the check boundary.

Globs in a configuration are relative to the config file that supplies them,
or to the invocation working directory when no config file governs the target.
Finding either anchor reads the filesystem and the working directory, and both
can fail for an environmental reason: a deleted working directory, an
unreadable parent, or an unresolved home directory.

That failure belongs to the file being checked. Resolving here, next to the
per-file check rather than inside rule execution, lets the check executor
report it against that file and carry on with the rest of the run. The
spelling decision itself stays in :mod:`stilyagi.config.paths`, which reads
nothing.
"""

import pathlib

from stilyagi.config.paths import config_relative_path

__all__ = ["config_relative_path_for"]


def config_relative_path_for(
    target: pathlib.Path,
    config_file: pathlib.Path | None,
) -> str:
    """Resolve the glob anchor and target, then spell the target purely.

    Resolving reads the filesystem, so this call can propagate the resolution's
    own failure. It raises nothing of its own: the caller owns the decision
    that such a failure is reported against the file being checked.

    Parameters
    ----------
    target:
        The path of the file being checked.
    config_file:
        The governing config file, or ``None`` when configuration is inline
        only or absent.

    Returns
    -------
    str
        The target path as POSIX text, relative to the glob anchor.

    Examples
    --------
    >>> from pathlib import Path
    >>> config_relative_path_for(
    ...     Path("/work/docs/a.md"), Path("/work/stilyagi.toml")
    ... )
    'docs/a.md'
    """
    anchor = (
        config_file.expanduser().resolve().parent
        if config_file is not None
        else pathlib.Path.cwd()
    )
    return config_relative_path(target.expanduser().resolve(), anchor)
