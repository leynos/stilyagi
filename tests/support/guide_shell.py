"""Run the shell commands a documentation example publishes.

The user's guide shows commands, pipelines, redirections, and standard input.
This module runs them as their real invocations in a caller-provided directory
and checks each exit status against the block's recorded expectation, so a
documented success cannot quietly become an operational failure. The file a
command promises to write is checked by the matching effect function.
"""

import io
import pathlib
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local interpreter invocation.
import sys
import typing as typ

from stilyagi.cli_args import build_parser

from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from tests.support.tested_examples import MarkedExample

__all__ = [
    "EFFECTS",
    "EXPECTED_STATUSES",
    "apply_effect",
    "check_shell",
]

#: Shell utilities a transcript may show beside a Stilyagi command. Only
#: `git` runs as part of a documented pipeline; the rest are illustrative.
SHELL_COMPANIONS: typ.Final[frozenset[str]] = frozenset({"git", "echo"})

#: Utilities a transcript shows but this module does not run.
ILLUSTRATIVE: typ.Final[frozenset[str]] = SHELL_COMPANIONS - {"git"}

#: The status each command line may exit with, in the order the block lists
#: them. A pipeline contributes one expectation per segment. `git apply`
#: accepts 0 or 128 in the pipe example because no shipped rule proposes a
#: safe fix, so the previewed patch is empty and git rejects it.
_OK: typ.Final[frozenset[int]] = frozenset({0})
EXPECTED_STATUSES: typ.Final[dict[str, tuple[frozenset[int], ...]]] = {
    "rules-invocations": (_OK,) * 5,
    "rule-invocations": (_OK,) * 2,
    "rule-unknown-code": (frozenset({2}),),
    "smoke-cli-entrypoint": (_OK,),
    "legacy-smoke-module-removal": (_OK,),
    "dump-ir-invocations": (_OK,) * 3,
    "diff-patch-to-file": (_OK, frozenset({0, 128})),
    "diff-patch-pipe": (_OK, frozenset({0, 128})),
    "fix-stdin-rewrite": (_OK,),
    "check-exit-code-invocations": (_OK,) * 8,
}


def _require(condition: object, message: str) -> None:
    """Raise ``AssertionError`` when a documented promise is broken."""
    if not condition:
        raise AssertionError(message)


def apply_effect(name: str, root: pathlib.Path) -> None:
    """Apply the file check a block's commands promise."""
    EFFECTS[name](root)


def apply_stdin_rewrite(root: pathlib.Path) -> None:
    """Require the stdin rewrite to write the repaired document to stdout."""
    written = root / "fixed.md"
    _require(written.exists(), "expected the rewrite to create fixed.md")
    original = (root / "README.md").read_text(encoding="utf-8")
    _require(
        written.read_text(encoding="utf-8") == original,
        "expected the unchanged document to be written through",
    )


def apply_patch_written(root: pathlib.Path) -> None:
    """Require a diff over a warning with no safe fix to write an empty patch."""
    patch = root / "fixes.patch"
    _require(patch.exists(), "expected the diff to create fixes.patch")
    _require(not patch.read_bytes(), "expected no safe fix to be previewed")


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


def _invocation(segment: str) -> list[str] | None:
    """Return the interpreter invocation one pipeline segment names."""
    tokens = shlex.split(_command_part(segment))
    if not tokens:
        return None
    if tokens[0] == "stilyagi":
        return [sys.executable, "-m", "stilyagi", *tokens[1:]]
    if tokens[0] == "python":
        return [sys.executable, *tokens[1:]]
    if tokens[0] == "git":
        return ["git", *tokens[1:]]
    return None


def _input_for(
    segment: str,
    root: pathlib.Path,
    stdin_bytes: bytes | None,
) -> bytes:
    """Return the bytes the segment reads from standard input."""
    source = _redirection(segment, "<")
    if source is not None:
        return (root / source).read_bytes()
    return stdin_bytes if stdin_bytes is not None else b""


def _stdout_for(
    segment: str,
    root: pathlib.Path,
) -> typ.IO[bytes] | int:
    """Return where the segment writes its standard output."""
    destination = _redirection(segment, ">")
    if destination is None:
        return subprocess.PIPE
    return (root / destination).open("wb")


def _run_segment(
    segment: str,
    root: pathlib.Path,
    stdin_bytes: bytes | None,
) -> tuple[int, bytes]:
    """Run one pipeline segment and return its status and standard output."""
    invocation = _invocation(segment)
    if invocation is None:
        message = f"expected a documented command in {segment!r}"
        raise AssertionError(message)
    input_bytes = _input_for(segment, root, stdin_bytes)
    destination_stream = _stdout_for(segment, root)
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
            invocation,
            cwd=root,
            env=python_module_environment(),
            input=input_bytes,
            stdout=destination_stream,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    finally:
        if isinstance(destination_stream, io.IOBase):
            destination_stream.close()

    _require(
        b"Traceback" not in completed.stderr,
        f"expected {segment!r} not to crash; got "
        f"{completed.stderr.decode(errors='replace')}",
    )
    return completed.returncode, completed.stdout or b""


def _run_command(
    example: MarkedExample,
    line: str,
    root: pathlib.Path,
    expected: cabc.Sequence[frozenset[int]],
) -> None:
    """Run one documented command line, pipeline and redirections included.

    Every segment must exit with a status the guide states for that block; a
    block with no recorded expectation fails, so a new example cannot be
    exercised without deciding what it promises.
    """
    standard_output: bytes | None = None
    segments = line.split("|")
    _require(
        len(segments) == len(expected),
        f"expected {example.name} to document {len(segments)} statuses",
    )
    for position, segment in enumerate(segments):
        status, standard_output = _run_segment(segment, root, standard_output)
        _require(
            status in expected[position],
            f"expected {example.name} segment {position} to exit "
            f"{sorted(expected[position])}, got {status}",
        )


def check_shell(example: MarkedExample, root: pathlib.Path) -> None:
    """Run every command in a transcript and parse it as well."""
    expected = EXPECTED_STATUSES.get(example.name)
    if expected is None:
        message = f"expected a documented exit status for {example.name}"
        raise AssertionError(message)
    commands = _commands(example)
    _require(bool(commands), f"expected {example.name} to show a command")
    position = 0
    for line in commands:
        tokens = shlex.split(_command_part(line))
        if tokens and tokens[0] in ILLUSTRATIVE:
            continue
        count = len(line.split("|"))
        _run_command(example, line, root, expected[position : position + count])
        position += count
        command = _command_part(line)
        if command:
            _check_parsed(example, command)
    _require(
        position == len(expected),
        f"expected {example.name} to document {position} statuses",
    )


def _check_parsed(example: MarkedExample, command: str) -> None:
    """Require the real parser to accept a Stilyagi command line."""
    tokens = shlex.split(command)
    if tokens[0] == "stilyagi":
        build_parser().parse_args(tokens[1:])
    elif tokens[0] not in SHELL_COMPANIONS and tokens[0] != "python":
        message = f"expected {example.name} to use a documented command"
        raise AssertionError(message)


EFFECTS: typ.Final[dict[str, cabc.Callable[[pathlib.Path], None]]] = {
    "fix-stdin-rewrite": apply_stdin_rewrite,
    "diff-patch-to-file": apply_patch_written,
}
