"""Bounded, path-free reporting for one extraction-cache invocation.

This module exists so that what a cache run *says* about itself is stated in
one place and separate from what it does. The counters and the storage timing
have one shared contract: every value is drawn from a fixed name, and no
record carries a source path, a cache path, a cache key, or an error message.
That is what lets them be logged on every invocation without leaking user input
into a log or into whatever later aggregates it.

The extraction service owns the decisions; this module only owns their
rendering, so a reader auditing what the cache reports need not read the
storage policy to do it.
"""

import contextlib
import dataclasses as dc
import logging
import time
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = ["CacheEventCounts", "storage_span"]

_LOGGER = logging.getLogger("stilyagi.cache.extraction")

#: The structured name every storage timing record carries.
STORAGE_OPERATION = "extraction_cache_storage"


@dc.dataclass(slots=True)
class CacheEventCounts:
    """Fixed, path-free event counters for one CLI invocation."""

    hits: int = 0
    misses: int = 0
    invalid: int = 0
    bypasses: int = 0
    write_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return stable counter names suitable for structured logging."""
        return {
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "cache_invalid": self.invalid,
            "cache_bypasses": self.bypasses,
            "cache_write_failures": self.write_failures,
        }


@contextlib.contextmanager
def storage_span(operation: str) -> cabc.Iterator[None]:
    """Time one storage operation as the completion of a bounded span.

    This record *is* the span. The service has no tracing subscriber, so a
    span that only opened and closed would be invisible; what a reader can use
    is the completed pair: a fixed operation label, the elapsed milliseconds,
    and nothing that identifies the file or its directory. Those three fields
    are the whole attribute set by design -- a path here would put user input
    into every log line and into anything that later aggregates them.

    The level is INFO rather than DEBUG because `--verbose` raises the root to
    INFO and no higher, so a DEBUG record would be computed and thrown away,
    which is exactly what the counters were before `dump-ir` grew a verbosity
    flag.

    Parameters
    ----------
    operation
        One of the fixed storage operations: ``open``, ``read`` or ``write``.

    Examples
    --------
    >>> with storage_span("read"):
    ...     pass  # a real call reads a cache entry here
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        _LOGGER.info(
            "persistent extraction cache storage %s",
            operation,
            extra={
                "operation": STORAGE_OPERATION,
                "outcome": operation,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            },
        )
