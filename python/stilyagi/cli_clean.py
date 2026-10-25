"""Run the top-level cleanup command for owned extraction-cache state."""

import pathlib
import sys
import typing as typ

from stilyagi.cache.clean import CacheCleanResult, clean_cache_tree


def run_clean(
    *,
    root: pathlib.Path | None = None,
    output: typ.TextIO | None = None,
    error: typ.TextIO | None = None,
) -> int:
    """Remove recognized caches beneath the invocation directory.

    Parameters
    ----------
    root
        Optional traversal root, defaulting to the current working directory.
    output, error
        Optional streams for embedding callers and tests.

    Returns
    -------
    int
        Zero when cleanup completes, or two if any eligible operation fails.

    Examples
    --------
    >>> from io import StringIO
    >>> import pathlib
    >>> run_clean(
    ...     root=pathlib.Path("."), output=StringIO(), error=StringIO()
    ... )  # doctest: +SKIP
    0
    """
    out_stream = output if output is not None else sys.stdout
    error_stream = error if error is not None else sys.stderr
    traversal_root = pathlib.Path.cwd() if root is None else root
    try:
        result = clean_cache_tree(traversal_root)
    except OSError as exc:
        error_stream.write(f"stilyagi clean: {exc}\n")
        return 2
    _render_result(result, out_stream, error_stream)
    return 2 if result.errors else 0


def _render_result(
    result: CacheCleanResult,
    output: typ.TextIO,
    error: typ.TextIO,
) -> None:
    """Render bounded counts and each cleanup failure to its command stream."""
    output.write(
        "cleaned "
        f"{result.removed_files} cache files in {result.removed_namespaces} "
        "namespaces; preserved "
        f"{result.preserved_unknown_entries} unknown entries\n"
    )
    error.writelines(f"stilyagi clean: {failure}\n" for failure in result.errors)
