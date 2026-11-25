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

#: A marker and its fence may be indented, as they are inside a list item.
_MARKER = re.compile(r"^[ \t]*<!-- tested-example: (?P<name>[A-Za-z0-9_-]+) -->[ \t]*$")
_FENCE = re.compile(r"^(?P<indent>[ \t]*)```(?P<language>[A-Za-z0-9_-]*)[ \t]*$")
#: A closing fence is backticks alone, optionally surrounded by whitespace.
_CLOSING_FENCE = re.compile(r"^[ \t]*```[ \t]*$")


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

    The style guide requires every fenced example to carry a marker, so an
    unmarked opening fence is an error rather than something to skip: skipping
    it would let a new example ship with no coverage while this loader still
    reported success.

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
        A fence has no preceding marker, a marker names no following block,
        two markers share a name, one marker immediately follows another, or a
        fence is not terminated.

    Examples
    --------
    >>> examples = load_tested_examples()
    >>> "projection-anomaly-record" in examples
    True
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    scan = _DocumentScan(lines=lines, document=path.name)
    examples = scan.collect()
    if scan.pending is not None:
        message = f"marker {scan.pending!r} names no fenced block"
        raise ValueError(message)
    return examples


@dc.dataclass(slots=True)
class _DocumentScan:
    """One pass over a document's markers and fenced blocks.

    A marker names the single block that follows it, so the scan holds that
    name pending until its block closes. Keeping the state here lets each
    rejection be decided where the document breaks the policy, rather than in
    one function that has to recognize every shape at once.
    """

    lines: cabc.Sequence[str]
    document: str
    examples: dict[str, MarkedExample] = dc.field(default_factory=dict)
    pending: str | None = None

    def collect(self) -> dict[str, MarkedExample]:
        """Scan the document and return the blocks closed so far.

        A marker still pending at the end of the document is left in
        :attr:`pending` for the caller to reject.

        Returns
        -------
        dict[str, MarkedExample]
            Each marked block, keyed by name.
        """
        index = 0
        while index < len(self.lines):
            index = self._consume(index)
        return self.examples

    def _consume(self, index: int) -> int:
        """Consume the line at ``index`` and return the index to resume from."""
        marker = _MARKER.match(self.lines[index])
        if marker is not None:
            self._accept_marker(marker.group("name"))
            return index + 1
        fence = _FENCE.match(self.lines[index])
        if fence is None:
            return index + 1
        return self._consume_block(index, fence)

    def _accept_marker(self, name: str) -> None:
        """Record ``name`` as pending, rejecting a marker that displaces one."""
        if self.pending is not None:
            message = (
                f"marker {self.pending!r} names no fenced block before marker {name!r}"
            )
            raise ValueError(message)
        self.pending = name

    def _consume_block(self, index: int, fence: re.Match[str]) -> int:
        """Read the block whose opening fence is at ``index`` and store it."""
        if self.pending is None:
            message = f"unmarked fence at line {index + 1} of {self.document}"
            raise ValueError(message)
        example, next_index = _read_block(self.lines, index, fence, self.pending)
        _store_example(self.examples, example)
        self.pending = None
        return next_index


def _read_block(
    lines: cabc.Sequence[str],
    index: int,
    fence: re.Match[str],
    name: str,
) -> tuple[MarkedExample, int]:
    """Read the marked block whose opening fence is at ``index``.

    Only a line that is entirely a closing fence ends the block, so a nested
    language-tagged fence such as a fenced block inside a shell transcript
    stays part of the content. Content is dedented by the opening fence's own
    indentation, which is how Markdown treats a block inside a list item.

    Returns
    -------
    tuple[MarkedExample, int]
        The block and the index after its closing fence.

    Raises
    ------
    ValueError
        The opening fence is never closed.
    """
    indent = len(fence.group("indent"))
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines) and not _CLOSING_FENCE.match(lines[cursor]):
        body.append(_strip_indent(lines[cursor], indent))
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


def _strip_indent(line: str, width: int) -> str:
    """Remove up to ``width`` leading spaces or tabs from ``line``."""
    leading = len(line) - len(line.lstrip(" \t"))
    return line[min(leading, width) :]


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
