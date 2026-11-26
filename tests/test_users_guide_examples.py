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
import pathlib
import re
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

_EXAMPLES = load_tested_examples()

#: The elapsed time a documented record cannot pin.
_ELAPSED = re.compile(r"elapsed_ms=\d+")

#: The record each text block must start with. Exact messages are asserted by
#: the command tests that produce them; this pins the record the guide shows.
_RECORD_PREFIXES: typ.Final[dict[str, str]] = {
    "verbose-progress-record": "INFO stilyagi.cli: ",
    "diff-rendered-record": "INFO stilyagi.check_outcome: ",
    "projection-anomaly-record": "projection recovered anomalies: ",
    "fix-error-synthetic-span": "fix-error/synthetic-span: ",
    "fix-error-changed-on-disk": "fix-error/changed-on-disk: ",
}

#: Shell utilities a transcript may show beside a Stilyagi command.
_SHELL_COMPANIONS: typ.Final[frozenset[str]] = frozenset({"git", "echo"})


def _assert_stdin_rewrite(root: pathlib.Path) -> None:
    """Require the stdin rewrite to write the repaired document to stdout."""
    written = root / "fixed.md"
    assert written.exists(), "expected the rewrite to create fixed.md"
    assert written.read_text(encoding="utf-8") == (root / "README.md").read_text(
        encoding="utf-8"
    ), "expected the unchanged document to be written through"


def _assert_patch_written(root: pathlib.Path) -> None:
    """Require a diff over a warning with no safe fix to write an empty patch."""
    patch = root / "fixes.patch"
    assert patch.exists(), "expected the diff to create fixes.patch"
    assert not patch.read_bytes(), "expected no safe fix to be previewed"


def _prepare_project(root: pathlib.Path) -> None:
    """Create the files the documented commands name."""
    docs = root / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Notes\n\nthe the thing.\n", encoding="utf-8")
    (root / "README.md").write_text("# Read me\n", encoding="utf-8")
    (root / "notes.mdc").write_text("# Notes\n", encoding="utf-8")


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


def _redirection(line: str, marker: str) -> pathlib.Path | None:
    """Return the path a transcript line redirects through ``marker``."""
    if marker not in line:
        return None
    return pathlib.Path(line.split(marker, 1)[1].strip().split()[0])


def _invocation(line: str) -> list[str] | None:
    """Return the interpreter invocation a transcript line names."""
    tokens = shlex.split(_command_part(line))
    if tokens[0] == "stilyagi":
        return [sys.executable, "-m", "stilyagi", *tokens[1:]]
    if tokens[0] == "python":
        return [sys.executable, *tokens[1:]]
    return None


def _run_command(example: MarkedExample, line: str, root: pathlib.Path) -> None:
    """Run one Stilyagi command and require a documented exit status.

    The guide documents statuses `0`, `1`, and `2`; a traceback or any other
    status is not a documented outcome. Redirection and standard input are
    honoured so a transcript's pipelines and file effects are exercised.
    """
    invocation = _invocation(line)
    if invocation is None:
        program = shlex.split(_command_part(line))[0]
        assert program in _SHELL_COMPANIONS, (
            f"expected {example.name} to use a documented command, not {program!r}"
        )
        return
    source = _redirection(line, "<")
    destination = _redirection(line, ">")
    source_stream = None if source is None else (root / source).open("rb")
    destination_stream = (
        None if destination is None else (root / destination).open("wb")
    )
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
            invocation,
            cwd=root,
            env=python_module_environment(),
            stdin=source_stream or subprocess.DEVNULL,
            stdout=destination_stream or subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    finally:
        if source_stream is not None:
            source_stream.close()
        if destination_stream is not None:
            destination_stream.close()

    assert completed.returncode in {0, 1, 2}, (
        f"expected {example.name} to exit 0, 1, or 2; got "
        f"{completed.returncode} and {completed.stderr.decode(errors='replace')}"
    )
    assert b"Traceback" not in completed.stderr, (
        f"expected {example.name} not to crash; got "
        f"{completed.stderr.decode(errors='replace')}"
    )


def _check_shell(example: MarkedExample, root: pathlib.Path) -> None:
    """Run every command in a transcript and parse it as well."""
    commands = _commands(example)
    assert commands, f"expected {example.name} to show a command"
    for line in commands:
        _run_command(example, line, root)
        command = _command_part(line)
        if command:
            _check_parsed(example, command)


def _check_parsed(example: MarkedExample, command: str) -> None:
    """Require the real parser to accept a Stilyagi command line."""
    tokens = shlex.split(command)
    if tokens[0] == "stilyagi":
        build_parser().parse_args(tokens[1:])
    elif tokens[0] not in _SHELL_COMPANIONS and tokens[0] != "python":
        pytest.fail(f"expected {example.name} to use a documented command")


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


def _collapse(text: str) -> str:
    """Collapse runs of whitespace so a wrapped record compares equal."""
    return " ".join(text.split())


def _emit_diff_record(example: MarkedExample, root: pathlib.Path) -> None:
    """Emit the diff record and compare it with the documented line.

    The run targets one file so `planned_files` matches the documented `1`;
    the target is named rather than left to discovery. The elapsed time varies
    between runs, so it is normalized; every other field and the message itself
    are compared exactly.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "stilyagi", "check", "--diff", "--verbose", "docs"],
        cwd=root,
        env=python_module_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
    )
    records = [
        line
        for line in completed.stderr.decode(errors="replace").splitlines()
        if "diff rendered" in line
    ]
    assert records, "expected the diff run to emit a rendered record"
    actual = _collapse(_ELAPSED.sub("elapsed_ms=0", records[0]))
    documented = _collapse(example.text)

    assert actual == documented, (
        f"expected the guide to show {actual!r}, not {documented!r}"
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


_EMITTERS: typ.Final[dict[str, cabc.Callable[[MarkedExample, pathlib.Path], None]]] = {
    "diff-rendered-record": _emit_diff_record,
}

_EFFECTS: typ.Final[dict[str, cabc.Callable[[pathlib.Path], None]]] = {
    "fix-stdin-rewrite": _assert_stdin_rewrite,
    "diff-patch-to-file": _assert_patch_written,
}


def _check_example(example: MarkedExample, root: pathlib.Path) -> None:
    """Dispatch one example to the check for its fence language."""
    emitter = _EMITTERS.get(example.name)
    if emitter is not None:
        emitter(example, root)
        return
    effect = _EFFECTS.get(example.name)
    if effect is not None:
        _check_shell(example, root)
        effect(root)
        return
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
