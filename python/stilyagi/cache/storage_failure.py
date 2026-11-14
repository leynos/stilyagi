"""Name cache storage failures in a form that is safe to log and count.

A `CacheStorageError` carries human detail that may name a path. That detail
belongs in a traceback and nowhere else: a log field or a metric label built
from it would leak the filesystem layout and, worse, would be unbounded.

`StorageFailureCategory` is the bounded alternative, and `storage_outcome`
composes it with the operation that failed into one stable, path-free string.
Both live here rather than beside the extraction service so the storage layer
can raise a categorized failure without importing the service that consumes it.
"""

import enum

__all__ = ["StorageFailureCategory", "storage_outcome"]


class StorageFailureCategory(enum.StrEnum):
    """Name why a cache operation could not stay inside owned storage.

    The values run from "this host or namespace cannot be used at all" to
    "this one entry is wrong", which is the order a reader needs when deciding
    whether to disable the cache entirely or merely skip a spoiled entry.
    """

    UNSAFE_OPERATIONS = enum.auto()
    MARKER_UNTRUSTED = enum.auto()
    NAMESPACE_REPLACED = enum.auto()
    LEASE_UNAVAILABLE = enum.auto()
    ENTRY_INVALID = enum.auto()
    RESTORE_FAILED = enum.auto()
    OWNERSHIP_REFUSED = enum.auto()


def storage_outcome(operation: str, category: StorageFailureCategory) -> str:
    """Name one storage fault as a bounded operation-and-category pair.

    Parameters
    ----------
    operation
        The short operation name, such as ``open``, ``read`` or ``write``.
    category
        The classified failure.

    Returns
    -------
    str
        An outcome such as ``storage_read_marker_untrusted``, built only from
        names the code controls. Neither part can carry a path or a payload.

    Examples
    --------
    >>> storage_outcome("read", StorageFailureCategory.MARKER_UNTRUSTED)
    'storage_read_marker_untrusted'
    """
    return f"storage_{operation}_{category.value}"
