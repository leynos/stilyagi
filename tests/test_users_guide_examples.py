"""Exercise every example the user's guide marks as tested.

The documentation style guide requires each fenced example in a user-facing
document to be executable and exercised. `load_tested_examples` rejects a fence
with no marker; this module rejects a marker with no consumer, so a block can
neither ship unmarked nor ship marked but unread.

Each example is checked according to its fence language. Python blocks run in a
fresh interpreter, TOML and JSON blocks are parsed, Markdown blocks go through
the extractor, shell blocks are parsed by the real command-line parser, and a
record block must start with a record the tool actually emits. A language with
no check fails rather than passing silently.
"""

import json
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local interpreter invocation.
import sys
import tomllib
import typing as typ

import pytest
from stilyagi import engine, model
from stilyagi.cli_args import build_parser

from tests.support.subprocess_env import python_module_environment
from tests.support.tested_examples import MarkedExample, load_tested_examples

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_EXAMPLES = load_tested_examples()

#: The record each text block must start with. Exact messages are asserted by
#: the command tests that produce them; this pins the record the guide shows.
_RECORD_PREFIXES: typ.Final[dict[str, str]] = {
    "verbose-progress-record": "INFO stilyagi.cli: ",
    "diff-rendered-record": "INFO stilyagi.cli: ",
    "projection-anomaly-record": "projection recovered anomalies: ",
    "fix-error-synthetic-span": "fix-error/synthetic-span: ",
    "fix-error-changed-on-disk": "fix-error/changed-on-disk: ",
}

#: Shell utilities a transcript may show beside a Stilyagi command.
_SHELL_COMPANIONS: typ.Final[frozenset[str]] = frozenset({"git", "echo"})


def _prepare_project(root: pathlib.Path) -> None:
    """Create the ``docs`` target the Python examples name."""
    docs = root / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Notes\n", encoding="utf-8")


def _run(
    example: MarkedExample,
    root: pathlib.Path,
    arguments: cabc.Sequence[str],
) -> None:
    """Run the interpreter with ``arguments`` and require a clean exit."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, *arguments],
        cwd=root,
        env=python_module_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, (
        f"expected {example.name} to run; stderr was "
        f"{completed.stderr.decode(errors='replace')}"
    )


def _run_python(example: MarkedExample, root: pathlib.Path) -> None:
    """Run one Python block in a fresh interpreter."""
    _run(example, root, ["-c", example.text])


def _run_python_module(
    example: MarkedExample, root: pathlib.Path, arguments: cabc.Sequence[str]
) -> None:
    """Run one ``python -m`` command from a transcript."""
    _run(example, root, ["-m", *arguments])


def _command_part(line: str) -> str:
    """Return a transcript line's command, before any pipe or redirection."""
    for separator in ("|", ">", "<"):
        line = line.split(separator, 1)[0]
    return line.strip()


def _commands(example: MarkedExample) -> list[str]:
    """Return the command lines of a transcript or command list.

    A transcript marks each command with `$ `; every other line is the output
    that command writes, which the command tests assert exactly. A block with
    no `$` prefix is a list of commands, so every line is one.

    Returns
    -------
    list[str]
        The command lines, with any `$ ` prompt removed.
    """
    if not any(line.startswith("$ ") for line in example.lines):
        return list(example.lines)
    return [line.removeprefix("$ ") for line in example.lines if line.startswith("$ ")]


def _check_command(
    example: MarkedExample,
    line: str,
    root: pathlib.Path,
) -> None:
    """Check one command line against the parser or its documented program."""
    command = _command_part(line)
    if not command:
        return
    tokens = shlex.split(command)
    if tokens[0] == "stilyagi":
        build_parser().parse_args(tokens[1:])
    elif tokens[:3] == ["python", "-m", "stilyagi.smoke"]:
        _run_python_module(example, root, tokens[2:])
    else:
        assert tokens[0] in _SHELL_COMPANIONS, (
            f"expected {example.name} to use a documented command, not {tokens[0]!r}"
        )


def _check_shell(example: MarkedExample, root: pathlib.Path) -> None:
    """Parse every command in a transcript and accept documented companions."""
    commands = _commands(example)
    assert commands, f"expected {example.name} to show a command"
    for line in commands:
        _check_command(example, line, root)


def _check_toml(example: MarkedExample) -> None:
    """Parse a TOML block with the interpreter's own parser."""
    tomllib.loads(example.text)


def _check_json(example: MarkedExample) -> None:
    """Parse a JSON block and require an object."""
    parsed = json.loads(example.text)
    assert isinstance(parsed, dict), f"expected {example.name} to encode an object"


def _check_markdown(example: MarkedExample) -> None:
    """Extract a Markdown block through the real extractor."""
    document = engine.extract_document(example.text, model.Syntax.MARKDOWN)
    assert document.syntax is model.Syntax.MARKDOWN, (
        f"expected {example.name} to extract as Markdown"
    )


def _check_record(example: MarkedExample) -> None:
    """Require a documented output record to start with its real record name."""
    prefix = _RECORD_PREFIXES.get(example.name)
    assert prefix is not None, (
        f"expected a record prefix for the text example {example.name}"
    )
    assert example.lines[0].startswith(prefix), (
        f"expected {example.name} to start with {prefix!r}"
    )


def _check_unknown_language(example: MarkedExample) -> None:
    """Fail an example whose fence language has no check."""
    pytest.fail(f"expected a check for the {example.language!r} example {example.name}")


def _check_example(example: MarkedExample, root: pathlib.Path) -> None:
    """Dispatch one example to the check for its fence language."""
    checks: dict[str, cabc.Callable[[], None]] = {
        "python": lambda: _run_python(example, root),
        "shell": lambda: _check_shell(example, root),
        "toml": lambda: _check_toml(example),
        "json": lambda: _check_json(example),
        "markdown": lambda: _check_markdown(example),
        "text": lambda: _check_record(example),
    }
    checks.get(example.language, lambda: _check_unknown_language(example))()


@pytest.mark.parametrize("name", sorted(_EXAMPLES))
def test_every_marked_example_is_exercised(name: str, tmp_path: pathlib.Path) -> None:
    """Every marked block in the guide runs, parses, or names a real record."""
    _prepare_project(tmp_path)

    _check_example(_EXAMPLES[name], tmp_path)
