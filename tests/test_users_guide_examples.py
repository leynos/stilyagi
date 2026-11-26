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
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local interpreter invocation.
import sys
import tomllib
import typing as typ

import pytest
from stilyagi import engine, model

from tests.support import guide_shell
from tests.support.subprocess_env import python_module_environment
from tests.support.tested_examples import MarkedExample, load_tested_examples

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_EXAMPLES = load_tested_examples()

#: The elapsed time a documented record cannot pin.
_ELAPSED = re.compile(r"elapsed_ms=\d+")

#: The record each remaining text block must start with. The two records the
#: CLI can emit deterministically are compared in full by their emitters; the
#: three below are produced by engine paths that need crafted inputs -- a
#: synthetic span, a file changed between planning and writing, and a
#: projection anomaly -- so their exact text is asserted by the tests that
#: build those inputs, and this pins the record name the guide shows.
_RECORD_PREFIXES: typ.Final[dict[str, str]] = {
    "verbose-progress-record": "INFO stilyagi.cli: ",
    "diff-rendered-record": "INFO stilyagi.check_outcome: ",
    "projection-anomaly-record": "projection recovered anomalies: ",
    "fix-error-synthetic-span": "fix-error/synthetic-span: ",
    "fix-error-changed-on-disk": "fix-error/changed-on-disk: ",
}


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
    documented = _collapse(_ELAPSED.sub("elapsed_ms=0", example.text))

    assert actual == documented, (
        f"expected the guide to show {actual!r}, not {documented!r}"
    )


def _emit_progress_record(example: MarkedExample, root: pathlib.Path) -> None:
    """Emit the progress record and compare it with the documented line."""
    completed = subprocess.run(
        [sys.executable, "-m", "stilyagi", "check", "--verbose", "docs"],
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
        if "check pass finished" in line
    ]
    assert records, "expected the verbose run to emit a progress record"
    actual = _collapse(_ELAPSED.sub("elapsed_ms=0", records[0]))
    documented = _collapse(_ELAPSED.sub("elapsed_ms=0", example.text))

    assert actual == documented, (
        f"expected the guide to show {actual!r}, not {documented!r}"
    )


def _emit_config_json(example: MarkedExample, root: pathlib.Path) -> None:
    """Emit the effective-config JSON and compare it with the documented block.

    JSON object key order is not a contract, so both sides are parsed and
    compared as values rather than as text.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stilyagi",
            "config",
            "lint.select",
            "--output-format",
            "json",
        ],
        cwd=root,
        env=python_module_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, (
        "expected the config query to succeed; got "
        f"{completed.stderr.decode(errors='replace')}"
    )

    assert json.loads(completed.stdout) == json.loads(example.text), (
        "expected the guide's config JSON to match the command's output"
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
    "config-effective-json": _emit_config_json,
    "diff-rendered-record": _emit_diff_record,
    "verbose-progress-record": _emit_progress_record,
}


def _check_example(example: MarkedExample, root: pathlib.Path) -> None:
    """Dispatch one example to the check for its fence language."""
    emitter = _EMITTERS.get(example.name)
    if emitter is not None:
        emitter(example, root)
        return
    if example.name in guide_shell.EFFECTS:
        guide_shell.check_shell(example, root)
        guide_shell.apply_effect(example.name, root)
        return
    checks: dict[str, cabc.Callable[[], None]] = {
        "python": lambda: _run_python(example, root),
        "shell": lambda: guide_shell.check_shell(example, root),
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
