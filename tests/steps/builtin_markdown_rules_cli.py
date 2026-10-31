"""Fresh-process BDD steps for config-relative rule scoping.

The other builtin-rule steps call ``cli.main`` in the test process, which
cannot show how a real invocation resolves its working directory. These steps
spawn ``python -m stilyagi`` instead, so the assertions are made against what a
shell would actually observe: the process's own working directory, its
discovered configuration, and the text it prints.

The scenarios pin the per-file-ignore anchor and the meaning of
``--stdin-filename``. A per-file glob is matched against the target's path
relative to the governing config file's directory, not relative to the
invocation directory; a piped document named with ``--stdin-filename`` is
resolved against the invocation directory. Each scoped case is paired with a
control that must report, so an ignore that never applied could not pass.
"""

import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the probe runs a trusted local interpreter.
import sys
import typing as typ

from pytest_bdd import given, parsers, then, when

from tests.support.assertions import assert_with_context
from tests.support.subprocess_env import python_module_environment

_BASE_CONFIG = '[lint]\nselect = ["STY", "MD"]\n'
_EXTENDING_CONFIG = (
    'extend = "base.toml"\n\n[lint.per-file-ignores]\n"docs/*.md" = ["STY"]\n'
)


class ScopingState(typ.TypedDict):
    """The scenario's repository, run options, and latest completed run."""

    root: pathlib.Path
    isolated: bool
    completed: subprocess.CompletedProcess[str] | None


def _run(
    cwd: pathlib.Path,
    args: list[str],
    *,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m stilyagi`` with the local package importable."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, "-m", "stilyagi", *args],
        cwd=cwd,
        env=python_module_environment(),
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _completed(state: ScopingState) -> subprocess.CompletedProcess[str]:
    """Return the scenario's completed run, failing when there is none."""
    completed = state["completed"]
    assert completed is not None, "expected a completed check invocation"
    return completed


def _output(state: ScopingState) -> str:
    """Return the run's combined output."""
    completed = _completed(state)
    return completed.stdout + completed.stderr


@given(
    'a repository whose extended config ignores STY for "docs/*.md"',
    target_fixture="scoping_state",
)
def a_repository_with_an_extended_per_file_ignore(
    tmp_path: pathlib.Path,
) -> ScopingState:
    """Write a repository whose config extends a base to add the glob."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "base.toml").write_text(_BASE_CONFIG, encoding="utf-8")
    (root / "stilyagi.toml").write_text(_EXTENDING_CONFIG, encoding="utf-8")
    return {"root": root, "isolated": False, "completed": None}


@given("configuration discovery is isolated")
def discovery_is_isolated(scoping_state: ScopingState) -> None:
    """Record that the next invocation must suppress configuration discovery."""
    scoping_state["isolated"] = True


@given(
    parsers.parse('a Markdown document under "{folder}" repeats the word "{word}"'),
)
def a_document_under_repeats(
    scoping_state: ScopingState,
    folder: str,
    word: str,
) -> None:
    """Write one document whose only finding is the repetition."""
    target = scoping_state["root"] / folder / "notes.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{word} {word}.\n", encoding="utf-8")


@when("I run stilyagi check from outside the repository on every document")
def run_from_outside(scoping_state: ScopingState) -> None:
    """Check both documents from a directory that holds no configuration."""
    root = scoping_state["root"]
    scoping_state["completed"] = _run(
        root.parent,
        ["check", str(root / "docs" / "notes.md"), str(root / "src" / "notes.md")],
    )


@when(
    parsers.parse(
        'I pipe the repeated word "{words}" to stilyagi check named "{name}"'
    ),
)
def pipe_named(
    scoping_state: ScopingState,
    words: str,
    name: str,
) -> None:
    """Check piped bytes whose name is resolved against the working directory.

    ``--isolated`` is appended only when an earlier step asked for it, keeping
    one command path for both the scoped and the isolation-control scenarios.
    """
    args = ["check", "-", "--stdin-filename", name]
    if scoping_state["isolated"]:
        args.append("--isolated")
    scoping_state["completed"] = _run(
        scoping_state["root"],
        args,
        stdin=f"{words}\n",
    )


@then("only the document outside the ignored tree reports STY001")
def only_the_unignored_document_reports(scoping_state: ScopingState) -> None:
    """Assert the glob was anchored at the config, not at the caller."""
    output = _output(scoping_state)

    assert_with_context(
        _completed(scoping_state).returncode == 0,
        "expected a warning-only run to exit zero",
    )
    assert_with_context(
        output.count("STY001") == 1,
        f"expected exactly one STY001 report, got {output!r}",
    )
    assert_with_context(
        "docs/notes.md" not in output,
        "expected the document under the ignored glob to report nothing",
    )
    assert_with_context(
        "src/notes.md" in output,
        f"expected the control document to report, got {output!r}",
    )


@then("no STY001 diagnostic is reported")
def no_sty001_is_reported(scoping_state: ScopingState) -> None:
    """Assert the piped document matched the ignored glob."""
    output = _output(scoping_state)

    assert_with_context(
        "STY001" not in output,
        f"expected the ignored piped document to report nothing, got {output!r}",
    )
    assert_with_context(
        "0 warnings" in _completed(scoping_state).stdout,
        "expected the summary to count no warnings",
    )


@then("STY001 is reported for the piped document")
def sty001_is_reported_for_the_stream(scoping_state: ScopingState) -> None:
    """Assert the control stream was not ignored."""
    completed = _completed(scoping_state)
    output = _output(scoping_state)

    assert_with_context(
        "STY001" in output,
        f"expected the control piped document to report, got {output!r}",
    )
    assert_with_context(
        "1 warnings" in completed.stdout,
        f"expected the summary to count one warning, got {completed.stdout!r}",
    )
