"""Tests for atomic, byte-preserving safe-fix file writes."""

import os
import stat
import typing as typ

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


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


def _unexpected_replace(_source: object, _target: object) -> typ.NoReturn:
    """Fail when a no-op write attempts to replace the target file."""
    message = "unexpected replacement for identical content"
    raise AssertionError(message)
