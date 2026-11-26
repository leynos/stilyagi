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
#: CommonMark opens a block at any indentation inside its container, then with
#: three or more backticks or tildes, then an optional info string.
_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
#: A block's language tag must be one this loader can name.
_LANGUAGE = re.compile(r"^[A-Za-z0-9_-]*$")
#: A closing fence is recognized at any indentation; `_closes` measures it
#: against the opening fence's container.
_CLOSING_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[ \t]*$")
#: A list item, whose content column is the indentation a nested fence uses.
_LIST_ITEM = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d+[.)])(?P<gap>[ \t]+)\S"
)


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
    container: int = 0

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
        self._track_container(self.lines[index])
        fence = _FENCE.match(self.lines[index])
        if fence is None or len(fence.group("indent")) > self.container + 3:
            self._require_pending_block()
            return index + 1
        language = self._accept_language(fence)
        return self._consume_block(index, fence, language)

    def _track_container(self, line: str) -> None:
        """Record the content column of the list item a fence may sit in.

        A list item's content starts after its marker, and a fence may be
        indented up to three spaces beyond that column. A non-blank line at
        column zero that is not a list item ends the list, so a top-level
        indented code block cannot open a fenced block.
        """
        if not line.strip():
            return
        item = _LIST_ITEM.match(line)
        if item is not None:
            self.container = (
                len(item.group("indent"))
                + len(item.group("marker"))
                + len(item.group("gap"))
            )
            return
        if not line.startswith((" ", "\t")):
            self.container = 0

    def _require_pending_block(self) -> None:
        """Reject a marker whose next line is not its fenced block.

        The style guide places the marker immediately before its fence, so a
        pending marker that meets prose names no block. Without this, a marker
        could bind to a fence much later in the document.

        Raises
        ------
        ValueError
            A marker is still pending when the line is neither a marker nor a
            fence.
        """
        if self.pending is not None:
            message = f"marker {self.pending!r} names no fenced block"
            raise ValueError(message)

    @staticmethod
    def _accept_language(fence: re.Match[str]) -> str:
        """Return the fence's language, rejecting an unsupported info string."""
        language = fence.group("info").strip()
        if not _LANGUAGE.fullmatch(language):
            message = f"unsupported fence info string {language!r}"
            raise ValueError(message)
        return language

    def _accept_marker(self, name: str) -> None:
        """Record ``name`` as pending, rejecting a marker that displaces one."""
        if self.pending is not None:
            message = (
                f"marker {self.pending!r} names no fenced block before marker {name!r}"
            )
            raise ValueError(message)
        self.pending = name

    def _consume_block(
        self,
        index: int,
        fence: re.Match[str],
        language: str,
    ) -> int:
        """Read the block whose opening fence is at ``index`` and store it."""
        if self.pending is None:
            message = f"unmarked fence at line {index + 1} of {self.document}"
            raise ValueError(message)
        opener = _Opener(
            fence=fence,
            indent=fence.group("indent"),
            language=language,
        )
        example, next_index = _read_block(self.lines, index, opener, self.pending)
        _store_example(self.examples, example)
        self.pending = None
        return next_index


@dc.dataclass(frozen=True, slots=True)
class _Opener:
    """The fence that opened a block, and the indentation it sets.

    The marker name is not part of this record: a block is read from the
    document, and the caller already holds the name it will be stored under.
    """

    fence: re.Match[str]
    indent: str
    language: str


def _read_block(
    lines: cabc.Sequence[str],
    index: int,
    opener: _Opener,
    name: str,
) -> tuple[MarkedExample, int]:
    """Read the marked block whose opening fence is at ``index``.

    Only a line that repeats the opening fence character at least as many
    times, with nothing else on it, ends the block. That keeps both a nested
    language-tagged fence and a shorter fence of the other character inside
    the content, as CommonMark does. Content is dedented by the opening
    fence's own indentation, which is how Markdown treats a block inside a
    list item.

    Returns
    -------
    tuple[MarkedExample, int]
        The block and the index after its closing fence.

    Raises
    ------
    ValueError
        The opening fence is never closed.
    """
    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines) and not _closes(lines[cursor], opener):
        body.append(_strip_indent(lines[cursor], len(opener.indent)))
        cursor += 1
    if cursor == len(lines):
        message = f"marker {name!r} has no closing fence"
        raise ValueError(message)
    example = MarkedExample(
        name=name,
        language=opener.language,
        lines=tuple(body),
    )
    return example, cursor + 1


def _closes(line: str, opener: _Opener) -> bool:
    """Return whether ``line`` closes the block ``opener`` started.

    The closing fence must use the same character, repeat it at least as many
    times, and be indented no more than three spaces beyond the opening
    fence's container. That keeps a deeper-indented fence inside the block,
    which is what a four-space-indented line in a column-zero block is.

    Returns
    -------
    bool
        Whether ``line`` ends the block.
    """
    closing = _CLOSING_FENCE.match(line)
    if closing is None:
        return False
    fence = closing.group("fence")
    opener_fence = opener.fence.group("fence")
    if fence[0] != opener_fence[0] or len(fence) < len(opener_fence):
        return False
    return len(closing.group("indent")) <= len(opener.indent) + 3


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
