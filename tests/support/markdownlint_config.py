"""Reading the Markdown linter's configuration, `.markdownlint-cli2.jsonc`.

The pure half takes text, so its cases can be driven on constructed
documents; the one file access goes through `workflow_files.read_text`,
the package's filesystem boundary. A configuration that does not parse,
or that declares no `ignores` array, is a `ReadingError` naming the
file rather than an empty list: every assertion over the result is
satisfied by an empty one, so an unreadable configuration must not look
like a compliant one.
"""

import json
import typing as typ

from tests.support.errors import ReadingError
from tests.support.workflow_files import read_text

if typ.TYPE_CHECKING:
    import pathlib


def without_comments(text: str) -> str:
    """Return JSONC text with its comments removed.

    Written out rather than imported, because no JSONC parser is in the
    development dependencies and the configuration is small. Handing
    the file to `json.loads` unchanged works only while nobody adds a
    comment, which is a strange thing to rely on for a file whose
    extension invites them.

    A regular expression would be the obvious shortcut and would be
    wrong: `//` inside a string literal is a path separator, not a
    comment, and stripping from it truncates the entry. So the scan
    tracks whether it is inside a string, and honours the escape.

    Parameters
    ----------
    text : str
        The JSONC document.

    Returns
    -------
    str
        The same document with `//` line comments and `/* */` block
        comments removed and everything else, including whitespace,
        left alone.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == '"':
            index = _copy_string(text, index, out)
            continue
        skipped = _skip_comment(text, index)
        if skipped is not None:
            index = skipped
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def _copy_string(text: str, start: int, out: list[str]) -> int:
    """Copy one string literal verbatim and return the index after it."""
    out.append(text[start])
    index = start + 1
    escaped = False
    while index < len(text):
        char = text[index]
        out.append(char)
        index += 1
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            break
    return index


def _skip_comment(text: str, index: int) -> int | None:
    """Return the index after a comment at this position, or None."""
    if text.startswith("//", index):
        end = text.find("\n", index)
        return len(text) if end == -1 else end
    if text.startswith("/*", index):
        end = text.find("*/", index + 2)
        return len(text) if end == -1 else end + 2
    return None


def configured_ignores(text: str, *, path: str) -> list[str]:
    """Return the `ignores` array one configuration's text declares.

    Parameters
    ----------
    text : str
        The configuration, as JSONC.
    path : str
        Where it came from, for the error.

    Returns
    -------
    list of str
        Its entries, in the order the file lists them.

    Raises
    ------
    ReadingError
        If it does not parse, is not an object, or declares no `ignores`
        array.
    """
    try:
        document = json.loads(without_comments(text))
    except json.JSONDecodeError as error:
        message = f"{path} is not JSONC: {error}"
        raise ReadingError(message, reader="configured_ignores", path=path) from error
    ignores = document.get("ignores") if isinstance(document, dict) else None
    if not isinstance(ignores, list):
        message = f"{path} must be an object declaring an `ignores` array"
        raise ReadingError(message, reader="configured_ignores", path=path)
    return [str(entry) for entry in ignores]


def read_configured_ignores(path: pathlib.Path) -> list[str]:
    """Return the `ignores` array the configuration file at `path` declares.

    A file that cannot be read raises `ReadingError` from `read_text`, and
    one `configured_ignores` refuses raises the same from there.

    Parameters
    ----------
    path : pathlib.Path
        The configuration file.

    Returns
    -------
    list of str
        Its entries, in the order the file lists them.
    """
    return configured_ignores(
        read_text(path, reader="configured_ignores"), path=str(path)
    )
