"""Tests for atomic, byte-preserving safe-fix file writes."""

import errno
import os
import stat
import typing as typ

import pytest

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import contextlib
    import pathlib


def test_write_source_replaces_content_and_preserves_mode(
    tmp_path: pathlib.Path,
) -> None:
    """Atomically replace bytes without changing the target permissions."""
    from stilyagi.engine.fix_planning.write import write_source

    target = tmp_path / "notes.md"
    target.write_bytes(b"before\r\n")
    target.chmod(0o640)

    write_source(target, b"after\r\n")

    assert target.read_bytes() == b"after\r\n", "expected replacement bytes"
    assert_with_context(
        stat.S_IMODE(target.stat().st_mode) == 0o640,
        "expected the replacement to preserve the original mode",
    )


def test_write_source_skips_identical_content(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid a replacement operation when a planned fix changes no bytes."""
    from stilyagi.engine.fix_planning.write import write_source

    target = tmp_path / "notes.md"
    original = b"unchanged\n"
    target.write_bytes(original)
    monkeypatch.setattr(os, "replace", _unexpected_replace)

    write_source(target, original)

    assert target.read_bytes() == original, "expected identical content to remain"


def test_write_source_updates_a_symlink_target_without_replacing_the_link(
    tmp_path: pathlib.Path,
) -> None:
    """Resolve file links so user-facing paths remain links after a fix."""
    from stilyagi.engine.fix_planning.write import write_source

    target = tmp_path / "target.md"
    link = tmp_path / "notes.md"
    target.write_bytes(b"before\n")
    link.symlink_to(target)

    write_source(link, b"after\n")

    assert link.is_symlink(), "expected the user-facing path to remain a symlink"
    assert target.read_bytes() == b"after\n", "expected the resolved target to change"


def test_write_source_refuses_a_target_edited_after_planning(
    tmp_path: pathlib.Path,
) -> None:
    """Refuse to overwrite an edit made between planning and writing."""
    from stilyagi.engine.fix_planning.write import (
        SourceChangedOnDiskError,
        write_source,
    )

    target = tmp_path / "notes.md"
    target.write_bytes(b"human edit\n")

    with pytest.raises(SourceChangedOnDiskError, match="changed on disk"):
        write_source(target, b"planned fix\n", original_bytes=b"planned\n")

    assert target.read_bytes() == b"human edit\n", "expected the edit to survive"


def test_write_source_applies_a_fix_when_the_original_bytes_still_match(
    tmp_path: pathlib.Path,
) -> None:
    """Apply the planned bytes when the target still holds the planned original."""
    from stilyagi.engine.fix_planning.write import write_source

    target = tmp_path / "notes.md"
    target.write_bytes(b"planned\n")

    write_source(target, b"planned fix\n", original_bytes=b"planned\n")

    assert target.read_bytes() == b"planned fix\n", "expected the planned fix"


def test_write_source_refuses_a_target_edited_during_staging(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse an edit that lands after staging but before the swap.

    The staging window is the dangerous one, and the check that ran before it
    cannot cover it: by the time the replacement bytes are on disk, a planning
    pass may have been in flight for minutes. Without a second comparison the
    swap would overwrite the intervening edit with bytes derived from a source
    that no longer exists -- silently, and with no refusal recorded.

    `shutil.copystat` is the deterministic hook for this window, because
    `write_source` calls it in the interval between staging the replacement and
    replacing the target. The stub performs the edit first and then copies the
    metadata, so the target changes at exactly the moment the old code would
    have stopped looking. Nothing here depends on timing or on a real
    concurrent writer.

    The edit has to survive *and* the staged file has to be gone: a refusal that
    left the temporary file behind would trade silent data loss for visible
    litter next to the user's source.
    """
    import shutil

    from stilyagi.engine.fix_planning.write import (
        SourceChangedOnDiskError,
        write_source,
    )

    target = tmp_path / "notes.md"
    target.write_bytes(b"planned\n")
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())
    real_copystat = shutil.copystat

    def edit_then_copy(source: object, destination: object) -> None:
        """Change the target, then preserve metadata as the real call would."""
        target.write_bytes(b"human edit during staging\n")
        real_copystat(source, destination)

    monkeypatch.setattr(shutil, "copystat", edit_then_copy)

    with pytest.raises(SourceChangedOnDiskError, match="changed on disk"):
        write_source(target, b"planned fix\n", original_bytes=b"planned\n")

    assert target.read_bytes() == b"human edit during staging\n", (
        "expected the mid-staging edit to survive the refusal"
    )
    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries, (
        "expected the refused write to leave no temporary file behind"
    )


def test_write_source_leaves_no_temporary_file_when_staging_fails(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove the staged temporary file when writing its bytes fails."""
    from stilyagi.engine.fix_planning import write as write_module

    target = tmp_path / "notes.md"
    target.write_bytes(b"before\n")
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())
    monkeypatch.setattr(write_module.os, "fdopen", _failing_fdopen)

    with pytest.raises(OSError, match="no space left"):
        write_module._write_temporary_source(target, b"after\n")

    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries, (
        "expected the failed staging attempt to leave no temporary file"
    )


def test_write_source_leaves_no_temporary_file_when_the_swap_fails(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove the staged file when the atomic swap itself fails.

    Staging and swapping are separate failure domains. The staging test above
    would still pass if the cleanup only covered ``_write_temporary_source``,
    yet a swap that raises before the rename -- a read-only parent directory,
    an exhausted inode table -- would then strand the temporary file beside the
    user's source. The assertion is on the directory listing rather than on the
    temporary name, because the failure is only observable through what is left
    behind.
    """
    import pathlib

    from stilyagi.engine.fix_planning import write as write_module

    target = tmp_path / "notes.md"
    target.write_bytes(b"before\n")
    before_entries = sorted(entry.name for entry in tmp_path.iterdir())
    monkeypatch.setattr(pathlib.Path, "replace", _failing_replace)

    with pytest.raises(OSError, match="read-only file system"):
        write_module.write_source(target, b"after\n")

    assert sorted(entry.name for entry in tmp_path.iterdir()) == before_entries, (
        "expected the failed swap to leave no temporary file behind"
    )
    assert target.read_bytes() == b"before\n", "expected the source to be intact"


def _failing_replace(self: pathlib.Path, _target: pathlib.Path) -> typ.NoReturn:
    """Fail the atomic swap the way a read-only parent directory would."""
    message = "read-only file system"
    raise OSError(errno.EROFS, message)


def _failing_fdopen(
    descriptor: int,
    _mode: str = "wb",
) -> contextlib.AbstractContextManager[typ.Any]:
    """Return a stream whose write fails, as a full disk would."""
    os.close(descriptor)

    class _FailingStream:
        """Context manager that raises on write and cleans up on exit."""

        def write(self, _payload: bytes) -> int:
            """Fail the staged write the way an exhausted device would."""
            raise OSError(errno.ENOSPC, "no space left on device")

        def __enter__(self) -> _FailingStream:
            """Return the stream so the ``with`` statement binds it."""
            return self

        def __exit__(self, *_exc_info: object) -> bool:
            """Propagate the staged write failure rather than suppressing it."""
            return False

    return _FailingStream()


def _unexpected_replace(_source: object, _target: object) -> typ.NoReturn:
    """Fail when a no-op write attempts to replace the target file."""
    message = "unexpected replacement for identical content"
    raise AssertionError(message)
