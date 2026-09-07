"""Atomically replace planned safe-fix source bytes on the same filesystem."""

import pathlib
import shutil
import tempfile


def write_source(path: pathlib.Path, content: bytes) -> None:
    r"""Replace source bytes atomically while preserving the target's metadata.

    Parameters
    ----------
    path:
        User-supplied file path whose resolved target is safe to replace.
    content:
        Planned UTF-8 source bytes to persist.

    Examples
    --------
    >>> from pathlib import Path
    >>> write_source(Path("notes.md"), b"Updated notes\\n")  # doctest: +SKIP
    """
    resolved_path = path.resolve()
    if resolved_path.read_bytes() == content:
        return
    temporary_path = _write_temporary_source(resolved_path, content)
    try:
        shutil.copystat(resolved_path, temporary_path)
        temporary_path.replace(resolved_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_temporary_source(path: pathlib.Path, content: bytes) -> pathlib.Path:
    """Write replacement bytes beside the target before its atomic swap."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        return pathlib.Path(temporary.name)
