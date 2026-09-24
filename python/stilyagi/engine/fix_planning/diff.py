"""Render unified patches for non-mutating safe-fix previews."""

import difflib

_NEWLINE = "\n"
_NO_NEWLINE_MARKER = "\\ No newline at end of file\n"


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
        _git_lines(before),
        _git_lines(after),
        fromfile=f"a/{reported_path}",
        tofile=f"b/{reported_path}",
        n=3,
    )
    return "".join(_terminated_diff_line(line) for line in lines)


def _git_lines(text: str) -> list[str]:
    r"""Split text on LF only, keeping terminators, as Git does.

    ``str.splitlines`` breaks on ``\r``, ``\v``, ``\f``, ``\x1c``-``\x1e``,
    ``\x85``, ``U+2028``, and ``U+2029``. Git recognises only ``\n``, so a
    Markdown line holding one of those characters would become two diff lines
    whose first element lacks a terminator. ``_terminated_diff_line`` would then
    insert a no-newline marker inside the hunk and corrupt the patch.

    Returns
    -------
    list[str]
        Each line with its ``\n`` terminator, except a final line that has none.

    Examples
    --------
    >>> _git_lines("one\ntwo")
    ['one\n', 'two']
    >>> _git_lines("one\n")
    ['one\n']
    >>> _git_lines("")
    []
    """
    parts = text.split(_NEWLINE)
    tail = parts.pop()
    lines = [f"{part}{_NEWLINE}" for part in parts]
    return [*lines, tail] if tail else lines


def _terminated_diff_line(line: str) -> str:
    """Append Git's missing-final-newline marker when a diff line lacks one."""
    if line.endswith(_NEWLINE):
        return line
    return f"{line}{_NEWLINE}{_NO_NEWLINE_MARKER}"
