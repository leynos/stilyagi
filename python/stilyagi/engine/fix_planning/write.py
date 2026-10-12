"""Atomically replace planned safe-fix source bytes on the same filesystem."""

import os
import pathlib
import shutil
import tempfile


class SourceChangedOnDiskError(OSError):
    """Raised when a file changed between planning a fix and writing it.

    The two-phase `--fix` flow (D-16) plans every file before writing any file.
    An edit made during that interval would otherwise be silently overwritten,
    so the writer only accepts a target that still holds the bytes the plan was
    derived from.
    """


def write_source(
    path: pathlib.Path,
    content: bytes,
    *,
    original_bytes: bytes | None = None,
) -> None:
    r"""Replace source bytes atomically while preserving the target's metadata.

    The staleness check runs twice, and the second run is load-bearing. Staging
    the replacement takes time -- it writes a file and copies metadata -- and
    nothing stops another writer from changing the target in that window. A
    single check before the swap would therefore cover only the interval before
    staging began, which is exactly the interval that a long planning pass has
    already left behind.

    **Residual race.** Two operations remain between the second check and the
    swap: `shutil.copystat` and `Path.replace`. Neither can be folded into the
    comparison, because the filesystem offers no compare-and-swap for a rename.
    A write landing in that last window is still lost. The guarantee this
    function gives is therefore "a target that changed before the swap begins is
    refused", not "a target can never be overwritten".

    Parameters
    ----------
    path:
        User-supplied file path whose resolved target is safe to replace.
    content:
        Planned UTF-8 source bytes to persist.
    original_bytes:
        Bytes the plan was derived from, when the plan is stale-sensitive.
        Passing these makes the write conditional: a target that no longer
        holds them is refused rather than overwritten.

    Raises
    ------
    SourceChangedOnDiskError
        The target no longer holds ``original_bytes``.

    Examples
    --------
    >>> from pathlib import Path
    >>> write_source(Path("notes.md"), b"Updated notes\\n")  # doctest: +SKIP
    """
    resolved_path = path.resolve()
    current_bytes = resolved_path.read_bytes()
    if original_bytes is not None and current_bytes != original_bytes:
        raise SourceChangedOnDiskError(_stale_target_message(resolved_path))
    if current_bytes == content:
        return
    temporary_path = _write_temporary_source(resolved_path, content)
    try:
        shutil.copystat(resolved_path, temporary_path)
        # Revalidate after staging, before the swap. This is the check that
        # covers the staging window; the one above cannot, because the window
        # had not opened yet when it ran.
        if original_bytes is not None and resolved_path.read_bytes() != original_bytes:
            raise SourceChangedOnDiskError(_stale_target_message(resolved_path))
        temporary_path.replace(resolved_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _stale_target_message(path: pathlib.Path) -> str:
    """Return the refusal text for a target that moved under its plan."""
    return (
        f"{path.as_posix()} changed on disk after it was planned; "
        "re-run the fix to plan against the current bytes"
    )


def _write_temporary_source(path: pathlib.Path, content: bytes) -> pathlib.Path:
    """Write replacement bytes beside the target before its atomic swap.

    ``mkstemp`` names the file before any bytes are written, so a failure while
    writing or closing it removes the partial file instead of leaving it beside
    the target.

    Returns
    -------
    pathlib.Path
        The staged file holding the replacement bytes.

    Raises
    ------
    OSError
        The replacement bytes could not be staged. The partial file is removed
        before the error propagates.
    """
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent)
    temporary_path = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path
