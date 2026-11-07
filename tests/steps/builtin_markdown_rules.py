"""BDD steps for the builtin Markdown rules through the real check command.

Unlike the fix-command scenarios, nothing here injects a rule runner: these
steps exercise the shipped builtin pack end to end, so a scenario fails if the
default selection, the extractor, or the renderer stops agreeing. Each
assertion is made against the bytes on disk and the command's own output,
which is the boundary a user actually sees.
"""

from __future__ import annotations

import json
import pathlib
import typing as typ

import pytest
from pytest_bdd import given, parsers, then, when
from stilyagi import cli

from tests.support.assertions import assert_with_context

#: The heading jump, the repeated word, and the banned term each scenario uses.
_HEADING_SOURCE = b"# Start\n### Detail\n"
_REPEAT_SOURCE = b"the the\n"


def _term_config(term: str) -> str:
    """Build a standalone config that opts in to TERM001 for one term."""
    return (
        "[lint]\n"
        'select = ["MD", "STY", "TERM"]\n'
        "\n"
        "[rule.TERM001]\n"
        f'terms = ["{term}"]\n'
    )


class RuleScenarioState(typ.TypedDict, total=False):
    """State shared across the builtin-rule scenarios."""

    root: pathlib.Path
    target: pathlib.Path
    original: bytes
    exit_code: int
    stdout: str
    stderr: str


def _scenario(
    tmp_path: pathlib.Path,
    source: bytes,
    *,
    config: str | None = None,
) -> RuleScenarioState:
    """Write the scenario's one Markdown file and optional configuration."""
    target = tmp_path / "notes.md"
    target.write_bytes(source)
    if config is not None:
        (tmp_path / "stilyagi.toml").write_text(config, encoding="utf-8")
    return {"root": tmp_path, "target": target, "original": source}


def _run(
    state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    """Run one check invocation in the scenario's tree and record it."""
    monkeypatch.chdir(state["root"])
    state["exit_code"] = cli.main(["check", *argv])
    captured = capsys.readouterr()
    state["stdout"] = captured.out
    state["stderr"] = captured.err


def _json_diagnostics(state: RuleScenarioState) -> list[dict[str, object]]:
    """Parse the recorded JSON output into its diagnostic list."""
    payload = json.loads(state["stdout"])
    return typ.cast("list[dict[str, object]]", payload["diagnostics"])


def _only_diagnostic(state: RuleScenarioState, code: str) -> dict[str, object]:
    """Return the one diagnostic carrying ``code``, failing on any other count."""
    matching = [
        diagnostic
        for diagnostic in _json_diagnostics(state)
        if diagnostic["code"] == code
    ]
    assert_with_context(
        len(matching) == 1,
        f"expected exactly one {code} diagnostic, got {matching}",
    )
    return matching[0]


@given(
    "a Markdown file has a level one heading followed by a level three heading",
    target_fixture="rule_scenario_state",
)
def a_heading_jump(tmp_path: pathlib.Path) -> RuleScenarioState:
    """Write a document whose second heading skips a level."""
    return _scenario(tmp_path, _HEADING_SOURCE)


@given(
    parsers.parse('a Markdown file contains the repeated words "{words}"'),
    target_fixture="rule_scenario_state",
)
def a_repeated_word(tmp_path: pathlib.Path, words: str) -> RuleScenarioState:
    """Write a document whose only finding is an adjacent repetition."""
    return _scenario(tmp_path, f"{words}\n".encode())


@given(
    parsers.parse('configuration selects TERM001 with the term "{term}"'),
    target_fixture="rule_scenario_state",
)
def configuration_selects_term001(
    tmp_path: pathlib.Path,
    term: str,
) -> RuleScenarioState:
    """Write a standalone config that opts in to the terminology rule."""
    return _scenario(tmp_path, b"", config=_term_config(term))


@given(
    parsers.parse('a Markdown paragraph contains "{text}"'),
)
def a_paragraph_contains(
    rule_scenario_state: RuleScenarioState,
    text: str,
) -> None:
    """Add the paragraph under the configured term document."""
    rule_scenario_state["target"].write_bytes(f"This is {text} wrong.\n".encode())


@when("I run stilyagi check on the file with JSON output")
def run_check_with_json(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the checker over the tree in JSON mode."""
    _run(rule_scenario_state, monkeypatch, capsys, [".", "--output-format", "json"])


@when("I run stilyagi check on the file")
def run_check(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the checker in JSON mode, the only format exposing byte spans."""
    _run(rule_scenario_state, monkeypatch, capsys, [".", "--output-format", "json"])


@when("I run stilyagi check with fixes enabled")
def run_check_with_fixes(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the safe fix pass, which must withhold the unsafe edit."""
    _run(rule_scenario_state, monkeypatch, capsys, [".", "--fix"])


@when("I run stilyagi check with unsafe fixes enabled")
def run_check_with_unsafe_fixes(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the fix pass with the explicit unsafe opt-in."""
    _run(rule_scenario_state, monkeypatch, capsys, [".", "--fix", "--unsafe-fixes"])


@then("the second heading has an MD001 source span and a manual fix")
def the_second_heading_has_an_md001_span(
    rule_scenario_state: RuleScenarioState,
) -> None:
    """Assert the structural finding addresses the whole second heading node."""
    diagnostic = _only_diagnostic(rule_scenario_state, "MD001")

    assert_with_context(
        diagnostic["span"] == {"byte_start": 8, "byte_end": 18},
        f"expected the second heading span (8, 18), got {diagnostic['span']}",
    )
    assert_with_context(
        diagnostic["fix_applicable"] is True,
        "expected MD001 to carry a manual fix entry",
    )


@then("applying fixes leaves the heading markers unchanged")
def applying_fixes_leaves_headings_unchanged(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Assert the manual fix writes nothing, even under ``--fix``."""
    _run(rule_scenario_state, monkeypatch, capsys, [".", "--fix"])

    assert_with_context(
        rule_scenario_state["target"].read_bytes() == _HEADING_SOURCE,
        "expected --fix to leave the heading markers byte-identical",
    )


@then("STY001 is reported and the source file is unchanged")
def sty001_is_reported_and_the_file_unchanged(
    rule_scenario_state: RuleScenarioState,
) -> None:
    """Assert the safe pass reports the repetition without touching the file."""
    assert_with_context(
        "STY001" in rule_scenario_state["stdout"] + rule_scenario_state["stderr"],
        "expected STY001 in the fix pass output",
    )
    assert_with_context(
        rule_scenario_state["exit_code"] == 0,
        "expected withholding the unsafe fix to be a successful run",
    )
    assert_with_context(
        rule_scenario_state["target"].read_bytes() == _REPEAT_SOURCE,
        "expected the safe pass to leave the source byte-identical",
    )
    assert_with_context(
        "--unsafe-fixes" in rule_scenario_state["stderr"],
        "expected the output to name the unsafe opt-in",
    )


@then("the repeated suffix is removed and verification re-lint is clean")
def the_suffix_is_removed_and_relint_is_clean(
    rule_scenario_state: RuleScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Assert the opt-in edit lands and a fresh check then finds nothing."""
    assert_with_context(
        rule_scenario_state["exit_code"] == 0,
        "expected the unsafe fix pass to exit 0",
    )
    assert_with_context(
        rule_scenario_state["target"].read_bytes() == b"the\n",
        "expected only the repeated suffix to be removed",
    )

    _run(rule_scenario_state, monkeypatch, capsys, ["."])

    assert_with_context(
        rule_scenario_state["exit_code"] == 0,
        "expected the verification re-lint to be clean",
    )


@then("TERM001 reports the exact original UTF-8 byte span")
def term001_reports_the_exact_span(
    rule_scenario_state: RuleScenarioState,
) -> None:
    """Assert the terminology finding addresses the configured token exactly."""
    diagnostic = _only_diagnostic(rule_scenario_state, "TERM001")

    assert_with_context(
        diagnostic["span"] == {"byte_start": 8, "byte_end": 17},
        f"expected the term span (8, 17), got {diagnostic['span']}",
    )


@then("no automatic fix is offered")
def no_automatic_fix_is_offered(rule_scenario_state: RuleScenarioState) -> None:
    """Assert the terminology rule never proposes an edit."""
    diagnostic = _only_diagnostic(rule_scenario_state, "TERM001")

    assert_with_context(
        diagnostic["fix"] is None and diagnostic["fix_applicable"] is False,
        f"expected no offered fix, got {diagnostic['fix_applicable']}",
    )
