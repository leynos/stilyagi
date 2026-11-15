"""Coordinate canonical extraction, cache identity, and fresh fallbacks."""

import collections.abc as cabc
import contextlib
import dataclasses as dc
import logging
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

from stilyagi import engine, model
from stilyagi.config.inspection import _config_table

from .identity import builtin_pack_signature, native_extension_digest
from .ir import InvalidCacheEntryError, decode_cache_entry, encode_cache_entry
from .lookup import (
    CacheAdapter,
    CacheExtractionInput,
    CacheLookup,
    CacheStoreFactory,
    Publication,
)
from .model import ExtractionRequest, cache_key
from .observability import CacheEventCounts, storage_span
from .storage import CacheStorageError, CacheStore, storage_outcome
from .storage_primitives import _absolute_lexical_path

__all__ = [
    "CacheExtractionInput",
    "CacheExtractionService",
    "CacheServiceConfig",
]

_LOGGER = logging.getLogger(__name__)

type ExtractionCallable = cabc.Callable[
    [str, model.Syntax, str | None], engine.ExtractionResult
]
type NativeDigestFactory = cabc.Callable[[], str]
type BuiltinSignatureFactory = cabc.Callable[[cabc.Mapping[str, object]], str]


@dc.dataclass(frozen=True, slots=True)
class CacheServiceConfig:
    """Fix cache identity, policy, and injectable collaborators per invocation.

    Parameters
    ----------
    invocation_cwd
        Working directory used to anchor relative cache paths. The command
        boundary supplies its own working directory here rather than letting
        the service read the ambient one, so a service is anchored where the
        command says it is.
    package_version
        Installed Stilyagi package version included in the cache key.
    no_cache
        Disable all persistent-cache operations for the invocation. A service
        can also be told this after construction with
        :meth:`CacheExtractionService.without_persistent_cache`, which is what
        the command boundaries use so the flag reaches an injected service.
    extractor, native_digest_factory, builtin_signature_factory, storage_factory
        Optional collaborators used by tests and embedding callers.
    """

    invocation_cwd: pathlib.Path
    package_version: str
    no_cache: bool = False
    extractor: ExtractionCallable | None = None
    native_digest_factory: NativeDigestFactory | None = None
    builtin_signature_factory: BuiltinSignatureFactory | None = None
    storage_factory: CacheStoreFactory | None = None


def _default_extractor(
    source_text: str,
    syntax: model.Syntax,
    source_path: str | None,
) -> engine.ExtractionResult:
    """Resolve the engine result adapter when each extraction runs."""
    return engine.extract_document_result(
        source_text,
        syntax,
        source_path=source_path,
    )


class CacheExtractionService:
    """Reuse validated Rust Markdown IR and retain a direct extraction path.

    The service constructor stores only invocation policy and injected
    factories. It performs no filesystem operation and does not fingerprint
    the extension until a cache-eligible Markdown request arrives. That makes
    ``no_cache=True`` a strict, testable zero-I/O bypass.
    """

    def __init__(self, settings: CacheServiceConfig) -> None:
        """Fix invocation-scoped policy and lazily supplied collaborators.

        Parameters
        ----------
        settings
            Paths, package identity, bypass choice, and optional test seams.
        """
        self.settings = settings
        self.invocation_cwd = settings.invocation_cwd
        self.package_version = settings.package_version
        self.no_cache = settings.no_cache
        self._extractor = (
            settings.extractor if settings.extractor is not None else _default_extractor
        )
        self._native_digest_factory = (
            settings.native_digest_factory
            if settings.native_digest_factory is not None
            else native_extension_digest
        )
        self._builtin_signature_factory = (
            settings.builtin_signature_factory
            if settings.builtin_signature_factory is not None
            else builtin_pack_signature
        )
        self._storage_factory = (
            settings.storage_factory
            if settings.storage_factory is not None
            else CacheStore
        )
        self._native_digest: str | None = None
        self._builtin_signatures: dict[tuple[str, ...], str] = {}
        self._stores: dict[pathlib.Path, CacheAdapter] = {}
        self._unusable_roots: set[pathlib.Path] = set()
        self.counters = CacheEventCounts()

    @contextlib.contextmanager
    def without_persistent_cache(self) -> cabc.Iterator[None]:
        """Forbid persistent-cache work for one invocation of this service.

        The boundaries call this when `--no-cache` was asked for, so the
        policy reaches an injected service as well as one they built. A
        service that has already opened storage keeps those descriptors until
        `close` and simply performs no further operations through them.

        The policy is saved and restored around the block: the bypass belongs
        to the invocation, not the service, so an embedding caller may reuse
        one service and a service configured ``no_cache=True`` keeps it.

        Examples
        --------
        >>> from pathlib import Path
        >>> from stilyagi.cache.extraction import (
        ...     CacheExtractionService,
        ...     CacheServiceConfig,
        ... )
        >>> service = CacheExtractionService(
        ...     CacheServiceConfig(
        ...         invocation_cwd=Path.cwd(), package_version="test-version"
        ...     )
        ... )
        >>> with service.without_persistent_cache():
        ...     service.no_cache
        True
        >>> service.no_cache
        False
        """
        saved_policy = self.no_cache
        self.no_cache = True
        try:
            yield
        finally:
            self.no_cache = saved_policy

    def lookup(self, request: CacheExtractionInput) -> CacheLookup:
        """Return a cache hit, or the fresh extraction to publish.

        This is a query: it opens the configured parent and namespace only
        when they already exist, publishes no ownership marker, and writes no
        entry. A miss therefore leaves the filesystem exactly as it found it,
        and :meth:`publish` is the separate command that persists the result.

        Parameters
        ----------
        request
            Source, identity and per-file settings for one extraction.

        Returns
        -------
        CacheLookup
            The extraction to return, the key that identified it, and the
            serialized bytes :meth:`publish` should store, or ``None`` when
            the request bypasses storage or has nothing worth storing.

        Examples
        --------
        >>> # A cold lookup reports a miss and writes no cache entry.
        >>> # See tests/test_extraction_cache.py for a real temporary directory.
        """
        if request.syntax is not model.Syntax.MARKDOWN:
            return CacheLookup(result=self._fresh(request))
        if self.no_cache or self._should_bypass(request):
            self._record_bypass("bypassed", "debug")
            return CacheLookup(result=self._fresh(request))
        return self._lookup_with_cache(request)

    def publish(self, lookup: CacheLookup) -> None:
        """Store the bytes one lookup prepared, when it has any.

        Parameters
        ----------
        lookup
            The result of :meth:`lookup` for this same request. Publishing
            the preparation the lookup made is what keeps the stored key and
            the stored bytes derived from one reading of the request.
        """
        if lookup.publication is None:
            return
        pending = lookup.publication
        try:
            with storage_span("write"):
                pending.store.create_namespace()
                pending.store.write(pending.key, pending.content)
        except CacheStorageError as error:
            self._event(storage_outcome("write", error.category), "warning")
            self.counters.write_failures += 1
            self._discard_store(pending.store_key)

    @staticmethod
    def _should_bypass(request: CacheExtractionInput) -> bool:
        """Return whether input origin or verification policy bypasses storage."""
        return any((request.from_stdin, request.force_fresh))

    def _lookup_with_cache(self, extraction_input: CacheExtractionInput) -> CacheLookup:
        """Return a valid hit, or prepare a miss for explicit publication."""
        normalized_config = _config_table(extraction_input.effective_config)
        try:
            request = self._request(extraction_input, normalized_config)
        except (ImportError, OSError, TypeError, ValueError) as error:
            self._record_bypass("identity_unavailable", "warning")
            _LOGGER.debug("cache identity unavailable: %s", error)
            return CacheLookup(result=self._fresh(extraction_input))

        key = cache_key(request)
        store_key = _absolute_lexical_path(
            extraction_input.cache_dir,
            self.invocation_cwd,
        )
        if store_key in self._unusable_roots:
            self.counters.bypasses += 1
            return CacheLookup(result=self._fresh(extraction_input))
        try:
            with storage_span("open"):
                store = self._store_for(extraction_input.cache_dir, store_key)
        except CacheStorageError as error:
            self._unusable_roots.add(store_key)
            self._record_bypass(storage_outcome("open", error.category), "warning")
            return CacheLookup(result=self._fresh(extraction_input))
        try:
            with storage_span("read"):
                cached = store.read(key)
        except CacheStorageError as error:
            self._record_bypass(storage_outcome("read", error.category), "warning")
            self._discard_store(store_key)
            return CacheLookup(result=self._fresh(extraction_input))

        hydrated = self._hydrate_cached(cached, key, request)
        if hydrated is not None:
            return CacheLookup(result=hydrated)
        self._event("miss", "debug")
        self.counters.misses += 1
        result = self._fresh(extraction_input)
        publication = (
            None
            if result.canonical_json is None
            else Publication(
                store=store,
                store_key=store_key,
                key=key,
                content=encode_cache_entry(key, result.canonical_json),
            )
        )
        return CacheLookup(result=result, publication=publication)

    def _hydrate_cached(
        self,
        content: bytes | None,
        key: str,
        request: ExtractionRequest,
    ) -> engine.ExtractionResult | None:
        """Return a valid cache hit and record malformed data as invalid."""
        if content is None:
            return None
        try:
            result = decode_cache_entry(content, key=key, request=request)
        except InvalidCacheEntryError:
            self._event("invalid", "debug")
            self.counters.invalid += 1
            return None
        self._event("hit", "debug")
        self.counters.hits += 1
        return result

    def _request(
        self,
        extraction_input: CacheExtractionInput,
        effective_config: dict[str, object],
    ) -> ExtractionRequest:
        """Build one immutable key request, computing invocation signatures lazily."""
        if self._native_digest is None:
            self._native_digest = self._native_digest_factory()
        plugins_value = effective_config.get("plugins", ())
        plugins = (
            tuple(plugins_value) if isinstance(plugins_value, (tuple, list)) else ()
        )
        if plugins not in self._builtin_signatures:
            self._builtin_signatures[plugins] = self._builtin_signature_factory(
                effective_config
            )
        return ExtractionRequest(
            source_text=extraction_input.source_text,
            syntax=extraction_input.syntax.value,
            reported_identity=extraction_input.reported_identity,
            effective_config=effective_config,
            native_extension_digest=self._native_digest,
            package_version=self.package_version,
            builtin_pack_signature=self._builtin_signatures[plugins],
        )

    def _store_for(
        self, cache_dir: pathlib.Path, store_key: pathlib.Path
    ) -> CacheAdapter:
        """Open one lazy store per normalized configured parent."""
        if store_key not in self._stores:
            self._stores[store_key] = self._storage_factory(
                cache_dir,
                invocation_cwd=self.invocation_cwd,
            )
        return self._stores[store_key]

    def _discard_store(self, store_key: pathlib.Path) -> None:
        """Close and forget a store after its path can no longer be trusted."""
        store = self._stores.pop(store_key, None)
        if store is not None:
            store.close()

    def _fresh(self, request: CacheExtractionInput) -> engine.ExtractionResult:
        """Run the injected or production Rust extraction adapter directly."""
        return self._extractor(
            request.source_text,
            request.syntax,
            request.reported_identity,
        )

    @staticmethod
    def _event(outcome: str, level: str) -> None:
        """Log one bounded, path-free cache event through the CLI boundary."""
        logger_method = getattr(_LOGGER, level)
        logger_method(
            "persistent extraction cache %s",
            outcome,
            extra={"operation": "extraction_cache", "outcome": outcome},
        )

    def _record_bypass(self, outcome: str, level: str) -> None:
        """Log and count one request that cannot use persistent storage."""
        self._event(outcome, level)
        self.counters.bypasses += 1

    def log_summary(self) -> None:
        """Log fixed invocation counters without exposing source paths."""
        if any(self.counters.as_dict().values()):
            _LOGGER.info(
                "persistent extraction cache summary",
                extra={
                    "operation": "extraction_cache_summary",
                    **self.counters.as_dict(),
                },
            )

    def close(self) -> None:
        """Close every lazily opened parent and namespace descriptor."""
        for store in tuple(self._stores.values()):
            store.close()
        self._stores.clear()
        self._unusable_roots.clear()
