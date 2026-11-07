"""Pure path spelling for config-relative glob matching.

This module decides only how a target is spelled once its resolved form and
the glob anchor are known. Resolving a path reads the filesystem and the
working directory, and either can fail for an environmental reason: a deleted
working directory, an unreadable parent, or an unresolved home directory. That
work belongs to :mod:`stilyagi.check_paths`, at the check boundary, which knows
the file being checked and can report the failure against it.

Keeping the spelling decision here also keeps it testable without a
filesystem.
"""

import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

__all__ = ["config_relative_path"]


def config_relative_path(target: pathlib.PurePath, anchor: pathlib.PurePath) -> str:
    """Return the POSIX spelling of a resolved target relative to its anchor.

    Globs are config-relative, anchored at the governing config file's parent,
    or at the invocation working directory when no config file governs the
    target. ``Path.relative_to(..., walk_up=True)`` gives a target outside the
    anchor the ``../`` walk-up spelling the globs expect. When no relative
    spelling exists at all, as when the target and anchor sit on different
    Windows drives, the resolved target is named absolutely instead of failing
    the check.

    Parameters
    ----------
    target:
        The already-resolved path of the file being checked.
    anchor:
        The already-resolved directory per-file globs are anchored at.

    Returns
    -------
    str
        The target path as POSIX text, relative to the glob anchor.

    Examples
    --------
    >>> from pathlib import Path
    >>> config_relative_path(Path("/work/docs/a.md"), Path("/work"))
    'docs/a.md'
    """
    try:
        return target.relative_to(anchor, walk_up=True).as_posix()
    except ValueError:
        # Different Windows drive or an unrelated anchor: no relative
        # spelling exists, so name the target absolutely rather than fail.
        return target.as_posix()
