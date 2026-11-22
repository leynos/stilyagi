"""Carry the outcome of a cache lookup and the publication it prepared.

The extraction cache separates reading from writing. A lookup answers "what
should this request return?" and, on a miss, also prepares the envelope that
would satisfy the same request next time. Publication is a separate command
that takes that preparation and stores it. Naming the preparation here is what
lets the two halves agree on one key and one set of bytes without the lookup
itself touching persistent storage.
"""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi import config, engine, model

__all__ = [
    "CacheAdapter",
    "CacheExtractionInput",
    "CacheLookup",
    "CacheStoreFactory",
    "Publication",
]


class CacheAdapter(typ.Protocol):
    """Narrow serialized-artefact operations used by the extraction policy."""

    def read(self, key: str, /) -> bytes | None:
        """Return one stored envelope or no entry."""

    def create_namespace(self) -> None:
        """Bring the configured namespace into being when it is absent."""

    def write(self, key: str, content: bytes, /) -> None:
        """Atomically store one already-serialized envelope."""

    def close(self) -> None:
        """Close storage descriptors held by the adapter."""


type CacheStoreFactory = cabc.Callable[..., CacheAdapter]


@dc.dataclass(frozen=True, slots=True)
class Publication:
    """The envelope one lookup prepared, ready for an explicit write.

    Parameters
    ----------
    store
        The adapter the lookup already opened for this request.
    store_key
        Normalized key identifying that adapter, so a failed write can
        discard exactly the store it invalidated.
    key
        The cache key the lookup computed for the request.
    content
        The serialized envelope for the extracted canonical IR.
    """

    store: CacheAdapter
    store_key: pathlib.Path
    key: str
    content: bytes


@dc.dataclass(frozen=True, slots=True)
class CacheExtractionInput:
    """Describe one file's source, effective config, and bypass policy.

    Parameters
    ----------
    source_text
        UTF-8-decoded source text read without newline translation.
    syntax
        Syntax selected by discovery for the input.
    reported_identity
        User-visible path embedded in canonical IR metadata.
    effective_config
        Resolved per-file configuration; provenance is excluded from keying.
    cache_dir
        Configured parent directory for this file's disposable cache.
    from_stdin
        Standard input always bypasses persistent storage.
    force_fresh
        Post-fix verification must extract the bytes written to disk again.
    """

    source_text: str
    syntax: model.Syntax
    reported_identity: str
    effective_config: config.StilyagiConfig
    cache_dir: pathlib.Path
    from_stdin: bool = False
    force_fresh: bool = False


@dc.dataclass(frozen=True, slots=True)
class CacheLookup:
    """Answer one extraction request without writing to persistent storage.

    Parameters
    ----------
    result
        The extraction the request should receive.
    publication
        The envelope an explicit publication command should store, or
        ``None`` when the request bypassed storage or produced nothing worth
        keeping.
    """

    result: engine.ExtractionResult
    publication: Publication | None = None
