"""Behavioural tests for the atomic replacement helper.

``scripts/atomic_write.py`` is the persistence primitive the duplication
allowlist writer depends on, so these tests pin its public contract directly
rather than through that caller: default parent creation, mode preservation
only when a destination exists, and the descriptor discipline around fsync.
"""

import dataclasses as dc
import inspect
import os
import stat
import tempfile
import typing as typ

import atomic_write
import pytest

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_creates_parent_directories_by_default(tmp_path: Path) -> None:
    """The default options create missing destination directories."""
    destination = tmp_path / "missing" / "nested" / "config.toml"

    atomic_write.atomic_write(destination, b"payload\n")

    assert destination.read_bytes() == b"payload\n", (
        "The destination must hold the replacement content."
    )


def test_without_parent_creation_requires_the_directory(tmp_path: Path) -> None:
    """Disabling parent creation surfaces a missing destination directory."""
    destination = tmp_path / "missing" / "config.toml"

    with pytest.raises(FileNotFoundError):
        atomic_write.atomic_write(
            destination,
            b"payload\n",
            options=atomic_write.AtomicWriteOptions(create_parents=False),
        )
    assert not destination.exists(), "A failed write must not create the destination."


def test_preserves_an_existing_destination_mode(tmp_path: Path) -> None:
    """Mode preservation copies the destination's permissions onto the replacement."""
    destination = tmp_path / "config.toml"
    destination.write_bytes(b"old\n")
    destination.chmod(0o640)

    atomic_write.atomic_write(
        destination,
        b"new\n",
        options=atomic_write.AtomicWriteOptions(preserve_mode=True),
    )

    assert destination.read_bytes() == b"new\n", "The content must be replaced."
    assert destination.stat().st_mode & 0o777 == 0o640, (
        "Mode preservation must retain the destination's permission bits."
    )


def test_preserves_mode_only_when_a_destination_exists(tmp_path: Path) -> None:
    """Mode preservation must not require an initial destination."""
    destination = tmp_path / "new" / "config.toml"

    atomic_write.atomic_write(
        destination,
        b"new\n",
        options=atomic_write.AtomicWriteOptions(preserve_mode=True),
    )

    assert destination.read_bytes() == b"new\n", (
        "A missing destination must still be created when preserving modes."
    )


def test_default_options_are_shared_rather_than_rebuilt() -> None:
    """The signature default is the module singleton, not a per-call construction."""
    default = inspect.signature(atomic_write.atomic_write).parameters["options"].default
    assert default is atomic_write._DEFAULT_OPTIONS, (
        "The default options must come from the module-level singleton."
    )


@dc.dataclass(slots=True)
class _OsSpy:
    """Record what ``atomic_write`` fsyncs, delegating the rest to ``os``.

    ``atomic_write`` closes every descriptor it syncs before it returns, so
    each descriptor is inspected while it is still open and the ``stat`` result
    kept; a later ``os.fstat`` on the recorded number would raise ``EBADF``.
    """

    #: The spy stands in for the whole ``os`` module, so the directory-sync
    #: helper's ``os.O_RDONLY`` has to resolve here too.
    O_RDONLY: typ.ClassVar[int] = os.O_RDONLY

    synced: list[os.stat_result] = dc.field(default_factory=list)

    def fsync(self, descriptor: int) -> None:
        """Record the descriptor's stat, then sync it for real."""
        self.synced.append(os.fstat(descriptor))
        os.fsync(descriptor)

    def open(self, path: Path, flags: int) -> int:
        """Delegate descriptor opening."""
        return os.open(path, flags)

    def close(self, descriptor: int) -> None:
        """Delegate descriptor closing."""
        os.close(descriptor)


@dc.dataclass(slots=True)
class _FailingDirectorySync:
    """Fail the directory sync, recording which descriptors get closed.

    The first ``fsync`` reaches the temporary file and is allowed through; the
    second reaches the directory and raises. ``atomic_write`` opens the
    directory through ``os.open``, so every descriptor recorded here is the
    directory descriptor, and the ``close`` calls show whether that descriptor
    was released on the failing path.
    """

    #: The spy stands in for the whole ``os`` module, so the directory-sync
    #: helper's ``os.O_RDONLY`` has to resolve here too.
    O_RDONLY: typ.ClassVar[int] = os.O_RDONLY

    syncs: int = 0
    opened: list[int] = dc.field(default_factory=list)
    closed: list[int] = dc.field(default_factory=list)

    def fsync(self, descriptor: int) -> None:
        """Sync the temporary file, then fail on the directory."""
        self.syncs += 1
        if self.syncs > 1:
            message = "directory sync failed"
            raise OSError(message)
        os.fsync(descriptor)

    def open(self, path: Path, flags: int) -> int:
        """Delegate descriptor opening, recording the descriptor."""
        descriptor = os.open(path, flags)
        self.opened.append(descriptor)
        return descriptor

    def close(self, descriptor: int) -> None:
        """Delegate descriptor closing, recording the descriptor."""
        self.closed.append(descriptor)
        os.close(descriptor)


def test_closes_the_directory_descriptor_when_the_sync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing directory sync must still release the descriptor it opened."""
    destination = tmp_path / "config.toml"
    spy = _FailingDirectorySync()
    monkeypatch.setattr(atomic_write, "os", spy)

    with pytest.raises(OSError, match="directory sync failed"):
        atomic_write.atomic_write(
            destination,
            b"payload\n",
            options=atomic_write.AtomicWriteOptions(sync_file=True),
        )

    assert len(spy.opened) == 1, "The directory descriptor must be opened once."
    assert spy.closed == spy.opened, (
        "The directory descriptor must be closed even when os.fsync raises."
    )
    assert not list(tmp_path.glob(f".{destination.name}.*")), (
        "A failed sync must not leave the temporary sibling behind."
    )


def test_syncs_the_temporary_file_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requesting a sync fsyncs the temporary file and the parent directory."""
    destination = tmp_path / "config.toml"
    spy = _OsSpy()
    monkeypatch.setattr(atomic_write, "os", spy)

    atomic_write.atomic_write(
        destination,
        b"payload\n",
        options=atomic_write.AtomicWriteOptions(sync_file=True),
    )

    assert len(spy.synced) == 2, "File and parent directory must each be fsynced."
    regular_files = [s for s in spy.synced if stat.S_ISREG(s.st_mode)]
    directories = [s for s in spy.synced if stat.S_ISDIR(s.st_mode)]
    assert len(regular_files) == 1, "Exactly one fsync must target the temporary file."
    assert len(directories) == 1, "Exactly one fsync must target the parent directory."
    assert destination.read_bytes() == b"payload\n", "The write must still complete."


@dc.dataclass(slots=True)
class _FailingTemporaryFile:
    """Stand in for ``tempfile`` and fail while the temporary is still open.

    Failing the write, the flush or the temporary file's own sync exercises the
    window before the replacement, which an earlier cleanup scope did not
    cover. A real file is still created under the naming pattern the caller
    asked for, so a missing cleanup leaves a sibling the assertions can see.
    """

    failure: str

    def NamedTemporaryFile(  # ruff: ignore[invalid-function-name] - tempfile's name.
        self, *, delete: bool, **kwargs: object
    ) -> _ExplodingStream:
        """Create a real temporary sibling whose stream fails on demand.

        ``delete`` is keyword-only and asserted rather than honoured: this
        double must leave the file on disk, so it can only stand in for the
        ``delete=False`` call the wrapper makes, and failing loudly here keeps
        a future change to that call from silently testing nothing.

        Returns
        -------
        _ExplodingStream
            A real temporary file that raises from the nominated method.
        """
        assert not delete, "The double can only model a retained temporary file."
        return _ExplodingStream(
            self.failure,
            directory=typ.cast("Path", kwargs["dir"]),
            prefix=typ.cast("str", kwargs["prefix"]),
        )


class _ExplodingStream:
    """A real temporary file that raises from one nominated method."""

    def __init__(self, failure: str, *, directory: Path, prefix: str) -> None:
        """Create the real temporary sibling the wrapper would have created."""
        self._failure = failure
        descriptor, name = tempfile.mkstemp(dir=directory, prefix=prefix)
        self._name = name
        self._stream = os.fdopen(descriptor, "wb")

    def __enter__(self) -> _ExplodingStream:
        """Return this stream for the caller's own ``with`` block."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close the underlying temporary file."""
        self._stream.close()

    @property
    def name(self) -> str:
        """Expose the temporary path the wrapper records for cleanup."""
        return self._name

    def __getattr__(self, attribute: str) -> object:
        """Delegate every attribute this double does not nominate to the file.

        ``os.fdopen`` gives a buffered stream whose ``name`` is the descriptor
        rather than the path, so ``name`` stays an explicit property. Everything
        else -- ``fileno`` above all -- is a genuine passthrough, and forwarding
        it generically keeps the double's surface to the failures it injects.

        Returns
        -------
        object
            Whatever the underlying temporary file holds for that attribute.

        Raises
        ------
        AttributeError
            If the attribute is asked for before the underlying file exists,
            which also keeps this method from recursing into itself.
        """
        try:
            stream = self.__dict__["_stream"]
        except KeyError:
            message = f"{type(self).__name__!r} has no attribute {attribute!r}"
            raise AttributeError(message) from None
        return getattr(stream, attribute)

    def write(self, content: bytes) -> int:
        """Write, or fail the way a full device does."""
        if self._failure == "write":
            raise OSError(28, "No space left on device")
        return self._stream.write(content)

    def flush(self) -> None:
        """Flush, or fail the way a broken device does."""
        if self._failure == "flush":
            raise OSError(5, "Input/output error")
        self._stream.flush()


@dc.dataclass(slots=True)
class _FailingSync:
    """Stand in for ``os`` and fail the temporary file's own sync.

    Every other lookup is delegated, so the temporary is still created through
    the real ``os`` and only the pre-replacement sync is disturbed. The
    directory sync is never reached, because the temporary one raises first.
    """

    def fsync(self, descriptor: int) -> typ.NoReturn:
        """Fail the way a broken device does."""
        message = "Input/output error"
        raise OSError(5, message)

    def __getattr__(self, attribute: str) -> object:
        """Delegate any other attribute to the real ``os`` module."""
        return getattr(os, attribute)


@pytest.mark.parametrize(
    ("failure", "diagnostic"),
    [
        ("write", "No space left on device"),
        ("flush", "Input/output error"),
        ("fsync", "Input/output error"),
    ],
    ids=["write", "flush", "temporary-sync"],
)
def test_early_write_failures_leave_no_temporary_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    diagnostic: str,
) -> None:
    """A failure before the replacement must not strand the temporary file.

    The destination is never at risk on these paths, because the replacement
    has not happened yet. What is at risk is the sibling written alongside it:
    an interrupted manifest write that leaves a hidden file behind would be
    picked up by the next reader of the directory as if it were real.
    """
    destination = tmp_path / "config.toml"
    destination.write_bytes(b"ORIGINAL\n")
    monkeypatch.setattr(atomic_write, "tempfile", _FailingTemporaryFile(failure))
    if failure == "fsync":
        monkeypatch.setattr(atomic_write, "os", _FailingSync())

    with pytest.raises(OSError, match=diagnostic):
        atomic_write.atomic_write(
            destination,
            b"REPLACEMENT\n",
            options=atomic_write.AtomicWriteOptions(sync_file=True),
        )

    assert destination.read_bytes() == b"ORIGINAL\n", (
        "A failed write must leave the destination untouched."
    )
    assert not list(tmp_path.glob(f".{destination.name}.*")), (
        "A failure before the replacement must not leave the temporary sibling."
    )


def test_a_failed_write_still_cleans_up_when_parents_are_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleanup covers a destination directory created by this call."""
    destination = tmp_path / "made" / "config.toml"
    monkeypatch.setattr(atomic_write, "tempfile", _FailingTemporaryFile("write"))

    with pytest.raises(OSError, match="No space left on device"):
        atomic_write.atomic_write(destination, b"REPLACEMENT\n")

    assert not destination.exists(), "A failed write must not create the destination."
    assert not list(destination.parent.glob(f".{destination.name}.*")), (
        "A created parent must not retain a stranded temporary file."
    )
