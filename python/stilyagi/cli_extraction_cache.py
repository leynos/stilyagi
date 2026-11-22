"""Select the extraction cache for a command and scope its bypass policy.

Both command boundaries -- `check` and `dump-ir` -- need the same three
decisions before they can extract a file: whether a caller supplied its own
cache, where to anchor a cache they did not, and how to apply `--no-cache`
for exactly this invocation. Keeping those decisions here means the two
commands cannot drift on what the flag means or on what happens when the
working directory cannot be read.
"""

import contextlib
import pathlib

from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cli_args import PACKAGE_VERSION

__all__ = ["cache_policy_for", "open_extraction_cache"]


def open_extraction_cache(
    injected: CacheExtractionService | None,
    *,
    invocation_cwd: pathlib.Path | None = None,
) -> CacheExtractionService:
    """Return the injected cache, or build one anchored at ``invocation_cwd``.

    The working directory is a parameter rather than something this function
    discovers, so a caller decides where its cache is anchored. Both command
    boundaries pass their own injected directory and leave the production
    invocation to supply the ambient one, which is the single place the
    process's working directory is read.

    A working directory that cannot be read is a cache root that cannot be
    anchored, so the service built here is one that never touches storage
    rather than one pointed at a substitute directory. Anchoring is what fails,
    not merely the lookup: every relative base re-reads the ambient working
    directory, so a substitute would only relocate the error to the first cache
    operation. The command then runs without persistent storage and reports its
    own result.

    Parameters
    ----------
    injected
        A caller's service, or ``None`` to build one over ``invocation_cwd``.
    invocation_cwd
        Directory to anchor a built service at, or ``None`` to read the
        process's ambient working directory.

    Returns
    -------
    CacheExtractionService
        The supplied service unchanged, or a new one.

    Examples
    --------
    >>> from pathlib import Path
    >>> from stilyagi.cache.extraction import (
    ...     CacheExtractionService,
    ...     CacheServiceConfig,
    ... )
    >>> service = CacheExtractionService(
    ...     CacheServiceConfig(invocation_cwd=Path.cwd(), package_version="1.0")
    ... )
    >>> open_extraction_cache(service, invocation_cwd=Path("/tmp")) is service
    True
    """
    if injected is not None:
        return injected
    anchor = invocation_cwd if invocation_cwd is not None else _ambient_directory()
    if anchor is None:
        return CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=pathlib.Path(),
                package_version=PACKAGE_VERSION,
                no_cache=True,
            )
        )
    return CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=anchor,
            package_version=PACKAGE_VERSION,
        )
    )


def _ambient_directory() -> pathlib.Path | None:
    """Read the process working directory, or None when it cannot be read."""
    try:
        return pathlib.Path.cwd()
    except OSError:
        return None


def cache_policy_for(
    extraction_cache: CacheExtractionService,
    *,
    no_cache: bool,
) -> contextlib.AbstractContextManager[None]:
    """Scope `--no-cache` to this invocation of the selected service.

    The flag is applied to the selected service, not only to one built here, so
    it means the same thing whether or not a caller injected a cache. It is
    applied through the service's own context manager rather than by assigning
    its attribute, because the bypass belongs to the invocation: an embedding
    caller may reuse one service across several runs.

    Parameters
    ----------
    extraction_cache
        The service the invocation will extract through.
    no_cache
        Whether this invocation asked for the bypass.

    Returns
    -------
    contextlib.AbstractContextManager
        A bypass for this block, or a context manager that does nothing.

    Examples
    --------
    >>> from pathlib import Path
    >>> from stilyagi.cache.extraction import (
    ...     CacheExtractionService,
    ...     CacheServiceConfig,
    ... )
    >>> service = CacheExtractionService(
    ...     CacheServiceConfig(invocation_cwd=Path.cwd(), package_version="1.0")
    ... )
    >>> with cache_policy_for(service, no_cache=True):
    ...     service.no_cache
    True
    >>> with cache_policy_for(service, no_cache=False):
    ...     service.no_cache
    False
    """
    if no_cache:
        return extraction_cache.without_persistent_cache()
    return contextlib.nullcontext()
