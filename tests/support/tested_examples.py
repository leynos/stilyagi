"""Load the user's guide examples that carry a `tested-example` marker.

The guide publishes command transcripts and output that a reader copies
verbatim. A test that repeats those literals drifts as soon as the guide is
edited, so the guide itself is the source: a marker comment names one block,
and a test loads the block from the Markdown file and asserts against it.

A marker applies to the single fenced block that follows it. The block's fence
language is recorded so a caller can tell a `shell` transcript from `text`
output, and the block's lines are returned without the fence.
"""

import dataclasses as dc
import pathlib
import re
import typing as typ

#: Repository root, so the guide resolves from any test's working directory.
REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

#: The guide a caller loads examples from, unless it names another document.
USERS_GUIDE: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "docs" / "users-guide.md"

_MARKER = re.compile(r"^<!-- tested-example: (?P<name>[A-Za-z0-9_-]+) -->$")
_FENCE = re.compile(r"^```(?P<language>[A-Za-z0-9_-]*)$")


@dc.dataclass(frozen=True, slots=True)
class MarkedExample:
    """One marked fenced block from a documentation file.

    Attributes
    ----------
    name:
        The marker's name, unique within the document.
    language:
        The fence's language tag, empty for an untagged block.
    lines:
        The block's lines, without the surrounding fences.
    """

    name: str
    language: str
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        """The block as one string, one newline per line.

        Returns
        -------
        str
            The block joined with newlines and ending in one newline.
        """
        return "\n".join(self.lines) + "\n"


def load_tested_examples(
    path: pathlib.Path = USERS_GUIDE,
) -> dict[str, MarkedExample]:
    """Return every marked block in ``path`` keyed by its marker name.

    Parameters
    ----------
    path:
        The Markdown document to read.

    Returns
    -------
    dict[str, MarkedExample]
        Each marked block, keyed by name.

    Raises
    ------
    ValueError
        A marker names no following fenced block, or two markers share a name.

    Examples
    --------
    >>> examples = load_tested_examples()
    >>> sorted(examples)[:1]
    ['projection-anomaly-record']
    """
    examples: dict[str, MarkedExample] = {}
    pending: str | None = None
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        marker = _MARKER.match(line)
        if marker is not None:
            pending = marker.group("name")
            index += 1
            continue
        fence = _FENCE.match(line)
        if fence is None or pending is None:
            index += 1
            continue
        language = fence.group("language")
        body: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith("```"):
            body.append(lines[index])
            index += 1
        if index == len(lines):
            message = f"marker {pending!r} has no closing fence"
            raise ValueError(message)
        if pending in examples:
            message = f"duplicate tested-example marker: {pending}"
            raise ValueError(message)
        examples[pending] = MarkedExample(
            name=pending,
            language=language,
            lines=tuple(body),
        )
        pending = None
        index += 1
    if pending is not None:
        message = f"marker {pending!r} names no fenced block"
        raise ValueError(message)
    return examples
