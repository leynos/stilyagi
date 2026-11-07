"""Name the environmental failures of expanding a user-relative path.

Configuration resolution expands ``~`` in the paths it reads, and
``Path.expanduser`` raises ``RuntimeError`` when it cannot determine the home
directory. That is an environmental failure the config phase must absorb and
report against the file being checked, but catching ``RuntimeError`` for it
would also swallow a programming error that happens to raise one.

Every expansion site therefore goes through :func:`expand_user` or
:func:`expand_and_resolve`, which convert that one failure into
:class:`PathResolutionError`. A caller catches exactly that type and lets every
other ``RuntimeError`` propagate.
"""

import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

__all__ = ["PathResolutionError", "expand_and_resolve", "expand_user"]


class PathResolutionError(RuntimeError):
    """A path could not be expanded because the home directory is unknown.

    ``Path.expanduser`` raises ``RuntimeError`` when it cannot determine the
    home directory, for example when the user database has no entry for the
    current user identifier. Raising this subclass at the expansion site keeps
    that environmental failure distinguishable from an unexpected runtime
    error, which a caller must not treat as an ordinary file failure.

    Examples
    --------
    >>> issubclass(PathResolutionError, RuntimeError)
    True
    """


def expand_user(path: pathlib.Path) -> pathlib.Path:
    """Expand ``~`` in ``path``, naming an unresolvable home directory.

    Parameters
    ----------
    path:
        The path to expand. An absolute or relative path without a leading
        ``~`` is returned unchanged.

    Returns
    -------
    pathlib.Path
        The expanded path, still unresolved.

    Raises
    ------
    PathResolutionError
        The home directory could not be determined.

    Examples
    --------
    >>> import pathlib
    >>> expand_user(pathlib.Path("docs"))
    PosixPath('docs')
    """
    try:
        return path.expanduser()
    except RuntimeError as exc:
        raise PathResolutionError(str(exc)) from exc


def expand_and_resolve(path: pathlib.Path) -> pathlib.Path:
    """Expand and resolve ``path``, naming an unresolvable home directory.

    Parameters
    ----------
    path:
        The path to expand and resolve.

    Returns
    -------
    pathlib.Path
        The absolute, symlink-resolved path.

    Notes
    -----
    An unresolvable home directory is re-raised as
    :class:`PathResolutionError`.

    Examples
    --------
    >>> import pathlib
    >>> expand_and_resolve(pathlib.Path("docs")).name
    'docs'
    """
    return expand_user(path).resolve()
