"""Process-boundary coverage for the builtin rule discovery commands.

The scenarios run the installed console script and the package module
entrypoint in disposable projects. They prove that the commands work before any
configuration is valid, that failures own standard error and leave standard
output empty, and that the `check` command still dispatches as before.
"""

import json
import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local console script.
import sys
import typing as typ

import pytest

from tests.support.subprocess_env import run_python_module

if typ.TYPE_CHECKING:
    from tests.support.subprocess_env import CapturedProcess


def _console_script() -> pathlib.Path:
    """Return the installed console script beside the running interpreter."""
    candidate = pathlib.Path(sys.executable).with_name("stilyagi")
    assert candidate.is_file(), f"expected the installed console script at {candidate}"
    return candidate


def _run_console(
    cwd: pathlib.Path,
    *arguments: str,
) -> CapturedProcess:
    """Run the installed console script with captured bytes."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted installed script, fixed argv, no shell.
        [_console_script(), *arguments],
        cwd=cwd,
        env=dict(os.environ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=60,
    )


def _write_malformed_project(root: pathlib.Path) -> None:
    """Write a Markdown source and a configuration no parser can read."""
    (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (root / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")


def test_console_rules_ignores_a_malformed_nearby_config(
    tmp_path: pathlib.Path,
) -> None:
    """The console script lists rules without reading broken configuration."""
    _write_malformed_project(tmp_path)

    completed = _run_console(tmp_path, "rules", "--output-format", "json")

    assert completed.returncode == 0, "expected static discovery to succeed"
    payload = json.loads(completed.stdout)
    assert [rule["code"] for rule in payload["rules"]] == [
        "DOC001",
        "DOC002",
        "DOC003",
        "MD001",
        "STY001",
        "TERM001",
    ], "expected the complete inventory"
    assert not completed.stderr, "expected no failure output"


def test_module_rules_succeeds_from_an_empty_directory(
    tmp_path: pathlib.Path,
) -> None:
    """No configuration or target is required to list the inventory."""
    completed = run_python_module(tmp_path, "rules")

    assert completed.returncode == 0, "expected an empty directory to succeed"
    assert completed.stdout.startswith(b"CODE"), "expected the list header"
    assert b"TERM001" in completed.stdout, "expected the opt-in rule"
    assert not completed.stderr, "expected no failure output"


def test_console_rule_detail_is_machine_readable(
    tmp_path: pathlib.Path,
) -> None:
    """One exact code renders a complete JSON descriptor."""
    completed = _run_console(tmp_path, "rule", "TERM001", "--output-format", "json")

    assert completed.returncode == 0, "expected the detail command to succeed"
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == 1, "expected schema version 1"
    assert payload["rule"]["code"] == "TERM001", "expected the requested rule"
    assert payload["rule"]["enabled_by_default"] is False, "expected an opt-in rule"
    assert not completed.stderr, "expected no failure output"


@pytest.mark.parametrize(
    ("arguments", "expected_stderr"),
    [
        pytest.param(
            ("rule", "UNKNOWN"),
            "unknown rule code: UNKNOWN",
            id="unknown-code",
        ),
        pytest.param(
            ("rule", "md001", "--output-format", "json"),
            "unknown rule code: md001",
            id="lower-case-is-a-miss",
        ),
        pytest.param(
            ("rule", "MD"),
            "unknown rule code: MD",
            id="prefix-is-a-miss",
        ),
    ],
)
def test_console_rule_errors_own_stderr_and_exit_two(
    tmp_path: pathlib.Path,
    arguments: tuple[str, ...],
    expected_stderr: str,
) -> None:
    """A lookup miss writes one actionable line and no result."""
    completed = _run_console(tmp_path, *arguments)

    assert completed.returncode == 2, "expected the operational-failure status"
    assert not completed.stdout, "expected empty standard output, even for JSON"
    assert expected_stderr.encode() in completed.stderr, (
        "expected the message to identify the requested code"
    )


def test_console_rule_escapes_control_characters_in_the_code(
    tmp_path: pathlib.Path,
) -> None:
    """A code containing a newline cannot break the one-line failure contract."""
    completed = _run_console(tmp_path, "rule", "BAD\nCODE")

    assert completed.returncode == 2, "expected the operational-failure status"
    assert not completed.stdout, "expected empty standard output"
    assert completed.stderr.count(b"\n") == 1, "expected exactly one stderr line"
    assert b"BAD\\nCODE" in completed.stderr, "expected the newline to be escaped"


def test_console_rules_filters_conjoin_to_an_empty_result(
    tmp_path: pathlib.Path,
) -> None:
    """Two filters that cannot both match succeed with the no-match sentence."""
    completed = _run_console(tmp_path, "rules", "--select", "MD", "--fixable", "yes")

    assert completed.returncode == 0, "expected an empty filtered list to succeed"
    assert completed.stdout == b"No builtin rules match the supplied filters.\n", (
        "expected the documented no-match sentence"
    )
    assert not completed.stderr, "expected no failure output"


def test_console_rules_rejects_an_invalid_enum(
    tmp_path: pathlib.Path,
) -> None:
    """The parser owns invalid filter values and exits two."""
    completed = _run_console(tmp_path, "rules", "--severity", "fatal")

    assert completed.returncode == 2, "expected the usage status"
    assert not completed.stdout, "expected no result for an invalid request"
    assert b"invalid choice" in completed.stderr.lower(), (
        "expected the parser's actionable message"
    )


def test_console_discovery_leaves_the_directory_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """Neither command writes a file into the working directory."""
    _write_malformed_project(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    assert _run_console(tmp_path, "rules").returncode == 0, "expected list success"
    assert _run_console(tmp_path, "rule", "STY001").returncode == 0, (
        "expected detail success"
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == before, (
        "expected no cache or output file to appear"
    )


def test_module_check_dispatch_is_preserved(tmp_path: pathlib.Path) -> None:
    """The default check command still discovers and lints a clean file."""
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")

    completed = run_python_module(tmp_path, "check", ".")

    assert completed.returncode == 0, "expected a clean check to succeed"
    assert completed.stdout.startswith(b"checked 1 files "), (
        "expected the check run summary"
    )
    assert not completed.stderr, "expected a clean check to write no errors"
