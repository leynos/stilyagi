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

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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
        A marker names no following fenced block, two markers share a name, or
        a fence is not terminated.

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
        index, pending = _consume_marker(lines, index, pending)
        if pending is None:
            index += 1
            continue
        block = _consume_fence(lines, index, pending)
        if block is None:
            index += 1
            continue
        example, index = block
        _store_example(examples, example)
        pending = None
    if pending is not None:
        message = f"marker {pending!r} names no fenced block"
        raise ValueError(message)
    return examples


def _consume_marker(
    lines: cabc.Sequence[str],
    index: int,
    pending: str | None,
) -> tuple[int, str | None]:
    """Return the index after ``lines[index]`` and the marker it carries.

    Returns
    -------
    tuple[int, str | None]
        The next index and the pending marker name, if the line is a marker.
    """
    marker = _MARKER.match(lines[index])
    return index, pending if marker is None else marker.group("name")


def _consume_fence(
    lines: cabc.Sequence[str],
    index: int,
    name: str,
) -> tuple[MarkedExample, int] | None:
    """Read the fenced block starting at ``index``, or return ``None``.

    Returns
    -------
    tuple[MarkedExample, int] | None
        The block and the index after its closing fence, or ``None`` when the
        line is not an opening fence.

    Raises
    ------
    ValueError
        The opening fence is never closed.
    """
    fence = _FENCE.match(lines[index])
    if fence is None:
        return None
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines) and not lines[cursor].startswith("```"):
        body.append(lines[cursor])
        cursor += 1
    if cursor == len(lines):
        message = f"marker {name!r} has no closing fence"
        raise ValueError(message)
    example = MarkedExample(
        name=name,
        language=fence.group("language"),
        lines=tuple(body),
    )
    return example, cursor + 1


def _store_example(
    examples: dict[str, MarkedExample],
    example: MarkedExample,
) -> None:
    """Record one example, rejecting a duplicate marker name.

    Raises
    ------
    ValueError
        Another example already uses this marker name.
    """
    if example.name in examples:
        message = f"duplicate tested-example marker: {example.name}"
        raise ValueError(message)
    examples[example.name] = example
