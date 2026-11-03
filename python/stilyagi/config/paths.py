"""Path spelling for config-relative glob matching.

Keep this separate from the check executor: the executor is already at the
project's module-length limit, and the spelling rule is a pure path decision
that does not need the run or its metrics.
"""

import pathlib

__all__ = ["config_relative_path"]


def config_relative_path(
    target: pathlib.Path,
    config_file: pathlib.Path | None,
) -> str:
    """Return the POSIX target path per-file ignore globs are matched against.

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
    >>> config_relative_path(Path("docs/a.md"), Path("stilyagi.toml"))
    'docs/a.md'
    """
    anchor = (
        config_file.expanduser().resolve().parent
        if config_file is not None
        else pathlib.Path.cwd()
    )
    resolved = target.expanduser().resolve()
    try:
        return resolved.relative_to(anchor, walk_up=True).as_posix()
    except ValueError:
        # Different Windows drive or an unrelated anchor: no relative
        # spelling exists, so name the target absolutely rather than fail.
        return resolved.as_posix()
