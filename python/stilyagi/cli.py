"""Command-line entrypoint placeholders for Stilyagi.

The roadmap has not landed the full end-user command surface yet, but the
package still needs a concrete CLI boundary that later slices can extend
without reshaping imports or entry points again. This module therefore keeps a
minimal placeholder path that proves the package can emit user-facing output
and that failures at that boundary return a non-zero process status.
"""

from __future__ import annotations

import sys


def _emit_placeholder_message() -> None:
    """Write the current placeholder CLI message to standard output."""
    print(
        "Stilyagi CLI skeleton is installed; feature commands land in later "
        "roadmap slices."
    )


def main() -> int:
    """Return the placeholder CLI exit status.

    The current skeleton path is intentionally small but still honours normal
    command-line behaviour: successful output returns zero, while output-layer
    failures are surfaced to standard error and produce a non-zero exit code.
    """
    try:
        _emit_placeholder_message()
    except OSError as error:
        print(f"stilyagi: failed to write CLI output: {error}", file=sys.stderr)
        return 1

    return 0
