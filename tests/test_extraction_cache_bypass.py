"""Verify extraction-cache failures, bypasses, and collaborator boundaries."""

import logging
import typing as typ

import pytest
from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cache.model import CACHE_NAMESPACE_NAME
from stilyagi.cache.storage import CacheStorageError
from stilyagi.config import StilyagiConfig

from tests.support.cache_extraction import (
    CacheTestRequest,
    counting_extractor,
    extract_cached_document,
    forbidden_cache_callback,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from stilyagi.cache.extraction import (
        BuiltinSignatureFactory,
        CacheStoreFactory,
        NativeDigestFactory,
    )


def test_cache_storage_failure_falls_back_to_uncached_extraction(
    tmp_path: pathlib.Path,
) -> None:
    """A failed atomic write does not change extraction output or exit flow."""
    calls: list[str] = []
    closed: list[bool] = []

    class WriteFailingStore:
        """Allow misses but reject publication after extraction succeeds."""

        def read(self, _key: str) -> bytes | None:
            """Treat every key as a cold request."""
            return None

        def write(self, _key: str, _content: bytes) -> None:
            """Simulate a cache filesystem failure such as disk full."""
            message = "injected disk-full write"
            raise CacheStorageError(message)

        def close(self) -> None:
            """Record that the unusable cache adapter was closed."""
            closed.append(True)

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
            native_digest_factory=lambda: "native-digest",
            builtin_signature_factory=lambda _config: "builtin-signature",
            storage_factory=lambda *_args, **_kwargs: WriteFailingStore(),
        )
    )
    config = StilyagiConfig(cache_dir=tmp_path / "cache")

    result = extract_cached_document(service, config)

    assert result.canonical_json is not None, (
        "storage failure must still return canonical IR"
    )
    assert calls == ["# Café\r\n"], "storage failure must not repeat extraction"
    assert service.counters.misses == 1, "the unavailable write follows one cold miss"
    assert service.counters.write_failures == 1, (
        "the failed publication must be counted"
    )
    assert closed == [True], "the failed storage adapter must be closed"
    service.close()


def test_cache_open_failure_warns_and_extracts_without_storage(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warn once per unusable cache root while each request still extracts."""
    calls: list[str] = []
    storage_attempts = 0

    def refuse_storage(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Simulate an unsafe or unavailable configured cache root."""
        nonlocal storage_attempts
        storage_attempts += 1
        message = "injected unavailable cache"
        raise CacheStorageError(message)

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
            native_digest_factory=lambda: "native-digest",
            builtin_signature_factory=lambda _config: "builtin-signature",
            storage_factory=refuse_storage,
        )
    )

    with caplog.at_level(logging.WARNING, logger="stilyagi.cache.extraction"):
        first = extract_cached_document(
            service, StilyagiConfig(cache_dir=tmp_path / "cache")
        )
        second = extract_cached_document(
            service,
            StilyagiConfig(cache_dir=tmp_path / "cache"),
            CacheTestRequest(identity="second.md"),
        )

    assert first.canonical_json is not None, "open failure must return canonical IR"
    assert second.canonical_json is not None, "later bypass must return canonical IR"
    assert calls == ["# Café\r\n", "# Café\r\n"], (
        "each file must still reach fresh extraction"
    )
    assert storage_attempts == 1, "an unusable cache root must be opened only once"
    assert service.counters.bypasses == 2, "each unavailable request counts as a bypass"
    warnings = tuple(
        record.getMessage()
        for record in caplog.records
        if record.name == "stilyagi.cache.extraction"
        and record.levelno == logging.WARNING
    )
    assert warnings == ("persistent extraction cache unavailable",), (
        "an unusable root must emit only one warning"
    )
    service.close()


def test_cache_read_failure_retries_store_construction_for_later_requests(
    tmp_path: pathlib.Path,
) -> None:
    """Treat read faults as request failures, not permanently unusable roots."""
    calls: list[str] = []
    storage_attempts = 0
    closed: list[bool] = []

    class ReadFailingStore:
        """Simulate a store that opens but cannot read its cache entry."""

        def read(self, _key: str) -> bytes | None:
            """Fail one cache lookup while leaving the root reopenable."""
            message = "injected transient read failure"
            raise CacheStorageError(message)

        def write(self, _key: str, _content: bytes) -> None:
            """Reject unexpected publication after the injected read failure."""
            pytest.fail("unexpected cache write after a read failure")

        def close(self) -> None:
            """Record that each failed adapter is discarded."""
            closed.append(True)

    def create_store(*_args: object, **_kwargs: object) -> ReadFailingStore:
        """Return a new store after counting each construction attempt."""
        nonlocal storage_attempts
        storage_attempts += 1
        return ReadFailingStore()

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor(calls),
            native_digest_factory=lambda: "native-digest",
            builtin_signature_factory=lambda _config: "builtin-signature",
            storage_factory=create_store,
        )
    )
    config = StilyagiConfig(cache_dir=tmp_path / "cache")

    first = extract_cached_document(service, config)
    second = extract_cached_document(
        service,
        config,
        CacheTestRequest(identity="second.md"),
    )

    assert first.canonical_json is not None, "read failure must return fresh extraction"
    assert second.canonical_json is not None, (
        "retry failure must return fresh extraction"
    )
    assert storage_attempts == 2, "later requests must retry a read-failed root"
    assert closed == [True, True], "each read-failed store must be closed"
    assert calls == ["# Café\r\n", "# Café\r\n"], (
        "each read-failed request must reach fresh extraction"
    )
    assert service.counters.bypasses == 2, "each read failure must count as a bypass"
    service.close()


def test_no_cache_constructs_no_storage_or_fingerprint_and_changes_no_cache_bytes(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
) -> None:
    """Avoid storage, fingerprinting, and persistent changes for no-cache."""
    warm_service, _ = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")
    extract_cached_document(warm_service, config)
    warm_service.close()
    namespace = config.cache_dir / CACHE_NAMESPACE_NAME
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in namespace.iterdir()
    }
    calls: list[str] = []
    forbidden = forbidden_cache_callback(
        "strict bypass reached a cache-only collaborator"
    )

    no_cache = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            no_cache=True,
            extractor=counting_extractor(calls),
            native_digest_factory=typ.cast("NativeDigestFactory", forbidden),
            builtin_signature_factory=typ.cast("BuiltinSignatureFactory", forbidden),
            storage_factory=typ.cast("CacheStoreFactory", forbidden),
        )
    )

    result = extract_cached_document(no_cache, config)
    no_cache.close()
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in namespace.iterdir()
    }

    assert result.canonical_json is not None, "no-cache mode must return canonical IR"
    assert calls == ["# Café\r\n"], "no-cache mode must extract exactly once"
    assert before == after, "no-cache mode must preserve the warm cache byte-for-byte"
    assert no_cache.counters.bypasses == 1, "no-cache extraction must count as a bypass"


def test_cold_no_cache_creates_no_cache_directory(tmp_path: pathlib.Path) -> None:
    """A cold direct extraction leaves no marker or cache parent behind."""
    cache_dir = tmp_path / "absent-cache"
    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            no_cache=True,
        )
    )

    result = extract_cached_document(service, StilyagiConfig(cache_dir=cache_dir))

    assert result.canonical_json is not None, (
        "cold no-cache mode must return canonical IR"
    )
    assert not cache_dir.exists(), "cold no-cache mode must not create its cache root"
    assert service.counters.bypasses == 1, (
        "cold no-cache extraction must count as a bypass"
    )
    service.close()


def test_cache_fingerprints_are_computed_once_per_invocation(
    tmp_path: pathlib.Path,
) -> None:
    """Reuse native and built-in signatures across distinct source requests."""
    native_calls = 0
    builtin_calls = 0

    def native_digest() -> str:
        """Count one loaded-extension identity calculation."""
        nonlocal native_calls
        native_calls += 1
        return "native-digest"

    def builtin_signature(_config: cabc.Mapping[str, object]) -> str:
        """Count one signature calculation for the enabled pack."""
        nonlocal builtin_calls
        builtin_calls += 1
        return "builtin-signature"

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            native_digest_factory=native_digest,
            builtin_signature_factory=builtin_signature,
        )
    )
    config = StilyagiConfig(cache_dir=tmp_path / "cache")

    extract_cached_document(service, config, CacheTestRequest(source="# First\n"))
    extract_cached_document(service, config, CacheTestRequest(source="# Second\n"))

    assert native_calls == 1, (
        "native extension identity must be computed once per invocation"
    )
    assert builtin_calls == 1, (
        "built-in pack identity must be computed once per invocation"
    )
    assert service.counters.misses == 2, (
        "each distinct source must produce one cold miss"
    )
    service.close()


@pytest.mark.parametrize("bypass", ["stdin", "post-fix"])
def test_stdin_and_post_fix_checks_bypass_a_warm_cache(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
    bypass: str,
) -> None:
    """Always extract stdin and post-fix bytes instead of using a warm hit."""
    service, calls = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")
    warm = extract_cached_document(service, config)
    fresh = extract_cached_document(
        service,
        config,
        CacheTestRequest(
            from_stdin=bypass == "stdin",
            force_fresh=bypass == "post-fix",
        ),
    )

    assert fresh == warm, "bypass extraction must preserve canonical IR"
    assert len(calls) == 2, "stdin and post-fix requests must each extract freshly"
    assert service.counters.hits == 0, "bypass requests must not use a warm entry"
    assert service.counters.bypasses == 1, (
        "the direct extraction must be counted as a bypass"
    )
    service.close()


@pytest.mark.parametrize("bypass", ["stdin", "post-fix"])
def test_stdin_and_post_fix_skip_storage_and_fingerprint_factories(
    tmp_path: pathlib.Path,
    bypass: str,
) -> None:
    """Take a direct path before any persistent-cache-only collaborator runs."""
    forbidden = forbidden_cache_callback(
        "fresh extraction reached a cache-only collaborator"
    )

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=counting_extractor([]),
            native_digest_factory=forbidden,
            builtin_signature_factory=forbidden,
            storage_factory=forbidden,
        ),
    )

    result = extract_cached_document(
        service,
        StilyagiConfig(cache_dir=tmp_path / "cache"),
        CacheTestRequest(
            from_stdin=bypass == "stdin",
            force_fresh=bypass == "post-fix",
        ),
    )

    assert result.canonical_json is not None, "fresh requests must return canonical IR"
    assert not (tmp_path / "cache").exists(), (
        "fresh requests must not create cache storage"
    )
    assert service.counters.bypasses == 1, (
        "fresh extraction must be counted as a bypass"
    )
    service.close()
