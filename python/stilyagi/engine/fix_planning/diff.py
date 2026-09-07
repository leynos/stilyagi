"""Render unified patches for non-mutating safe-fix previews."""

import difflib


def unified_diff(before: str, after: str, reported_path: str) -> str:
    """Render a Git-applicable unified diff for one file.

    Parameters
    ----------
    before:
        Original decoded source text.
    after:
        Planned decoded source text.
    reported_path:
        Repository-relative path shown in the patch headers.

    Returns
    -------
    str
        An empty string for identical text, otherwise a unified patch that
        preserves original line endings and missing trailing newlines.
    """
    if before == after:
        return ""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{reported_path}",
        tofile=f"b/{reported_path}",
        n=3,
    )
    return "".join(_terminated_diff_line(line) for line in lines)


def _terminated_diff_line(line: str) -> str:
    """Append Git's missing-final-newline marker when a diff line lacks one."""
    if line.endswith("\n"):
        return line
    return f"{line}\n\\ No newline at end of file\n"
