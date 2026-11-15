"""Hold the cache read path to a query and publication to an explicit command.

The extraction cache used to persist as a side effect of a query: opening the
configured root with `create=True`, writing the ownership marker and publishing
the miss entry were all reachable from the call that answered "what should this
request return?". These tests hold the separation that replaced it, because a
split only means something if a lookup cannot write and a command cannot store
without asking to.

The command cases inject both the working directory and the store, and the
store records the order of its calls. Asserting that order is what distinguishes
"the publish happens to follow the lookup" from "the lookup itself wrote".
"""

import dataclasses as dc
import io
import typing as typ

import pytest
from stilyagi import cli, cli_dump_ir, model
from stilyagi.cache.extraction import (
    CacheExtractionInput,
    CacheExtractionService,
    CacheServiceConfig,
)
from stilyagi.cache.model import CACHE_NAMESPACE_NAME
from stilyagi.cli_args import CheckOptions, DumpIrOptions
from stilyagi.config import StilyagiConfig

from tests.support.cache_extraction import counting_extractor

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.cache.lookup import CacheLookup

#: The source every case runs over; one heading is enough to be cacheable.
SOURCE = "# Café\r\n"

#: The configured parent a full publication creates.
CACHE_PARENT = ".stilyagi_cache"

#: The command names these cases are parameterized over.
COMMANDS = ("check", "dump-ir")


@dc.dataclass(slots=True)
class RecordingStore:
    """Record every storage call, in the order the service makes it."""

    calls: list[str]
    entries: dict[str, bytes] = dc.field(default_factory=dict)

    def read(self, key: str) -> bytes | None:
        """Record the read and answer from the entries written so far."""
        self.calls.append("read")
        return self.entries.get(key)

    def create_namespace(self) -> None:
        """Record that storage was brought into being."""
        self.calls.append("create_namespace")

    def write(self, key: str, content: bytes) -> None:
        """Record the write and retain the bytes for a later read."""
        self.calls.append("write")
        self.entries[key] = content

    def close(self) -> None:
        """Record that the store was closed."""


def _recording_service(root: pathlib.Path) -> tuple[CacheExtractionService, list[str]]:
    """Build a service over a store that records its own call order."""
    calls: list[str] = []
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=root,
            package_version="test-version",
            extractor=counting_extractor([]),
            storage_factory=lambda *_args, **_kwargs: RecordingStore(calls),
        )
    )
    return service, calls


def _cold_lookup(
    service: CacheExtractionService,
    *,
    identity: str = "notes.md",
) -> CacheLookup:
    """Look one stable Markdown request up in ``service`` without publishing."""
    config = StilyagiConfig(cache_dir=service.invocation_cwd / CACHE_PARENT)
    return service.lookup(
        CacheExtractionInput(
            source_text=SOURCE,
            syntax=model.Syntax.MARKDOWN,
            reported_identity=identity,
            effective_config=config,
            cache_dir=config.cache_dir,
        )
    )


def _namespace(root: pathlib.Path) -> pathlib.Path:
    """Return the owned namespace under one configured cache parent."""
    return root / CACHE_PARENT / CACHE_NAMESPACE_NAME


def test_a_cold_lookup_creates_no_cache_storage(tmp_path: pathlib.Path) -> None:
    """Answer a miss, and bring nothing into being while doing so."""
    calls: list[str] = []
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
        )
    )
    try:
        lookup = _cold_lookup(service)

        assert lookup.publication is not None, (
            "a cold miss must prepare the envelope a publish could store"
        )
        assert calls == [SOURCE], "a cold lookup must extract exactly once"
        assert service.counters.misses == 1, "a cold lookup must count one miss"
        assert not (tmp_path / CACHE_PARENT).exists(), (
            "a lookup must not create the configured cache parent"
        )
        assert not _namespace(tmp_path).exists(), (
            "a lookup must not create the cache namespace or its owner marker"
        )
    finally:
        service.close()


def test_a_lookup_only_reads_the_store(tmp_path: pathlib.Path) -> None:
    """Reach the store's read and nothing that could persist."""
    service, store_calls = _recording_service(tmp_path)
    try:
        service.lookup(_request(service))

        assert store_calls == ["read"], (
            f"a lookup must read and never publish, got {store_calls}"
        )
    finally:
        service.close()


def _request(service: CacheExtractionService) -> CacheExtractionInput:
    """Build the cacheable request the recording-store cases reuse."""
    config = StilyagiConfig(cache_dir=service.invocation_cwd / CACHE_PARENT)
    return CacheExtractionInput(
        source_text=SOURCE,
        syntax=model.Syntax.MARKDOWN,
        reported_identity="notes.md",
        effective_config=config,
        cache_dir=config.cache_dir,
    )


def test_publishing_is_the_only_route_to_a_stored_entry(
    tmp_path: pathlib.Path,
) -> None:
    """Store nothing until the explicit publication command is called."""
    calls: list[str] = []
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
        )
    )
    try:
        lookup = _cold_lookup(service)
        assert not _namespace(tmp_path).exists(), (
            "the lookup must leave the namespace absent"
        )

        service.publish(lookup)

        assert _namespace(tmp_path).is_dir(), (
            "an explicit publish must create the namespace"
        )
        assert service.counters.write_failures == 0, (
            "a publication over a writable parent must succeed"
        )

        warm = _cold_lookup(service)
        assert service.counters.hits == 1, (
            "the published entry must serve the next read"
        )
        assert warm.publication is None, "a hit has nothing to publish"
        assert calls == [SOURCE], "a warm lookup must not reach the extractor"
    finally:
        service.close()


def test_publishing_a_hit_writes_nothing(tmp_path: pathlib.Path) -> None:
    """Treat publication of a hit as the no-op it is, not a rewrite."""
    service, store_calls = _recording_service(tmp_path)
    try:
        service.publish(_cold_lookup(service))
        assert store_calls == ["read", "create_namespace", "write"], (
            f"a miss publishes once, in order, got {store_calls}"
        )

        service.publish(_cold_lookup(service))

        assert store_calls == [
            "read",
            "create_namespace",
            "write",
            "read",
        ], "publishing a hit must not create or write anything"
        assert service.counters.write_failures == 0, (
            "a hit has nothing to store, so nothing can fail"
        )
    finally:
        service.close()


@pytest.mark.parametrize("command", COMMANDS)
def test_a_default_command_run_publishes_the_entry_it_extracted(
    tmp_path: pathlib.Path,
    command: str,
) -> None:
    """Prove the explicit publish is reachable from both command surfaces.

    The operand is absolute and the command is anchored at ``tmp_path`` through
    its own collaborator seam, so the case pins where the boundary takes its
    invocation directory from instead of relying on the test process's own.
    """
    target = tmp_path / "notes.md"
    target.write_bytes(SOURCE.encode())

    assert _run_command(command, target, tmp_path) == 0, (
        f"a default {command} run must succeed"
    )

    assert _namespace(tmp_path).is_dir(), (
        f"a default {command} run must publish the entry it extracted"
    )
    assert any(path.is_file() for path in _namespace(tmp_path).iterdir()), (
        f"the {command} run must leave at least one stored entry"
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_a_default_command_run_reads_before_it_creates(
    tmp_path: pathlib.Path,
    command: str,
) -> None:
    """Publish only after the read that established the miss.

    The order is the whole point of the split: a store that was created and
    written before it was read would mean the command persisted on the way to
    answering, which is what the reviewer's query/command rule forbids.
    """
    target = tmp_path / "notes.md"
    target.write_bytes(SOURCE.encode())
    calls: list[str] = []
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor([]),
            storage_factory=lambda *_args, **_kwargs: RecordingStore(calls),
        )
    )
    try:
        status = _run_command(
            command, target, tmp_path, cache=_InjectedCache(service=service)
        )
    finally:
        service.close()

    assert status == 0, f"a default {command} run must succeed"
    assert calls == ["read", "create_namespace", "write"], (
        f"{command} must read, then create, then publish; got {calls}"
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_an_injected_cache_under_no_cache_performs_no_storage_calls(
    tmp_path: pathlib.Path,
    command: str,
) -> None:
    """Reach no storage collaborator at all when the flag is given."""
    target = tmp_path / "notes.md"
    target.write_bytes(SOURCE.encode())
    calls: list[str] = []
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
            storage_factory=lambda *_args, **_kwargs: RecordingStore([]),
        )
    )
    try:
        status = _run_command(
            command,
            target,
            tmp_path,
            cache=_InjectedCache(service=service, no_cache=True),
        )
    finally:
        service.close()

    assert status == 0, "a strict bypass must succeed through an injected cache"
    assert calls == [SOURCE], f"expected one extraction, got {calls}"
    assert not (tmp_path / CACHE_PARENT).exists(), (
        "a strict bypass must not create cache storage"
    )


@dc.dataclass(frozen=True, slots=True)
class _InjectedCache:
    """The cache a command run is given, and whether it may write to it."""

    service: CacheExtractionService | None = None
    no_cache: bool = False


#: A run that injects no cache at all, letting the production default apply.
DEFAULT_CACHE = _InjectedCache()


def _run_command(
    command: str,
    target: pathlib.Path,
    root: pathlib.Path,
    *,
    cache: _InjectedCache = DEFAULT_CACHE,
) -> int:
    """Run one command with its operand, directory and cache injected."""
    if command == "check":
        return cli.run_check(
            CheckOptions(targets=(str(target),), no_cache=cache.no_cache),
            collaborators=cli.CheckCollaborators(
                output=io.StringIO(),
                extraction_cache=cache.service,
                invocation_cwd=root,
            ),
        )
    return cli_dump_ir.run_dump_ir(
        DumpIrOptions(targets=(str(target),), no_cache=cache.no_cache),
        collaborators=cli_dump_ir.DumpIrCollaborators(
            output=io.BytesIO(),
            cache=cache.service,
            invocation_cwd=root,
        ),
    )
