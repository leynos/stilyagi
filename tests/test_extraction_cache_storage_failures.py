"""Verify cache storage failures preserve fresh extraction behavior."""

import errno
import logging
import typing as typ

import pytest
from stilyagi.cache import storage as cache_storage
from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cache.model import CACHE_NAMESPACE_NAME
from stilyagi.cache.storage import CacheStorageError
from stilyagi.config import StilyagiConfig

from tests.support.cache_extraction import (
    CacheServiceRegistrar,
    CacheTestRequest,
    counting_extractor,
    extract_cached_document,
)

if typ.TYPE_CHECKING:
    import pathlib


def test_cache_storage_failure_falls_back_to_uncached_extraction(
    tmp_path: pathlib.Path,
    close_cache_services: CacheServiceRegistrar,
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

    service = close_cache_services(
        CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version="test-version",
                extractor=counting_extractor(calls),
                native_digest_factory=lambda: "native-digest",
                builtin_signature_factory=lambda _config: "builtin-signature",
                storage_factory=lambda *_args, **_kwargs: WriteFailingStore(),
            )
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
    close_cache_services: CacheServiceRegistrar,
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

    service = close_cache_services(
        CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version="test-version",
                extractor=counting_extractor(calls),
                native_digest_factory=lambda: "native-digest",
                builtin_signature_factory=lambda _config: "builtin-signature",
                storage_factory=refuse_storage,
            )
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


def test_os_permission_error_opening_namespace_falls_back_to_extraction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    close_cache_services: CacheServiceRegistrar,
) -> None:
    """Normalize cache mkdir faults so extraction can safely bypass storage."""
    calls: list[str] = []
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    refused: list[str] = []
    storage_attempts = 0

    def create_store(
        cache_path: pathlib.Path,
        *,
        invocation_cwd: pathlib.Path,
    ) -> cache_storage.CacheStore:
        """Count the real storage boundary before opening its namespace."""
        nonlocal storage_attempts
        storage_attempts += 1
        return cache_storage.CacheStore(
            cache_path,
            invocation_cwd=invocation_cwd,
        )

    service = close_cache_services(
        CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version="test-version",
                extractor=counting_extractor(calls),
                native_digest_factory=lambda: "native-digest",
                builtin_signature_factory=lambda _config: "builtin-signature",
                storage_factory=create_store,
            )
        )
    )
    original_mkdir = cache_storage.os.mkdir

    def refuse_namespace(
        path: str
        | bytes
        | cache_storage.os.PathLike[str]
        | cache_storage.os.PathLike[bytes],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        """Refuse only the namespace create, preserving configured-root setup."""
        if path == CACHE_NAMESPACE_NAME:
            refused.append(str(path))
            raise PermissionError(errno.EACCES, "denied")
        original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(cache_storage.os, "mkdir", refuse_namespace)
    monkeypatch.setattr(
        cache_storage.os,
        "supports_dir_fd",
        {*cache_storage.os.supports_dir_fd, refuse_namespace},
    )
    try:
        result = extract_cached_document(
            service,
            StilyagiConfig(cache_dir=cache_dir),
        )
        assert result.canonical_json is not None, (
            "a cache permission failure must still return canonical IR"
        )
        assert calls == ["# Café\r\n"], "permission failure must extract once"
        assert storage_attempts == 1, "the request must reach real cache storage"
        assert refused == [CACHE_NAMESPACE_NAME], (
            "the test must inject a namespace creation failure"
        )
        assert service.counters.bypasses == 1, (
            "the unavailable cache must be counted as a bypass"
        )
    finally:
        service.close()


def test_cache_read_failure_retries_store_construction_for_later_requests(
    tmp_path: pathlib.Path,
    close_cache_services: CacheServiceRegistrar,
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

    service = close_cache_services(
        CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version="test-version",
                extractor=counting_extractor(calls),
                native_digest_factory=lambda: "native-digest",
                builtin_signature_factory=lambda _config: "builtin-signature",
                storage_factory=create_store,
            )
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
