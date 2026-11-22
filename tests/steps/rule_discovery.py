"""BDD steps for builtin rule discovery through the real CLI process.

The scenarios live in ``features/rule_discovery.feature``. Most run
``python -m stilyagi`` in a disposable directory, which is what proves the
commands work without a valid project. The one in-process read is the
documented TERM001 example: the step takes the TOML the catalogue publishes,
writes it as a real ``pyproject.toml``, and lints the documented source through
the command boundary, so the printed guidance is itself executable.
"""

import json
import pathlib
import typing as typ

from pytest_bdd import given, parsers, then, when
from stilyagi.rules.catalogue import get_rule

from tests.support.subprocess_env import CapturedProcess, run_python_module


class RuleDiscoveryState(typ.TypedDict, total=False):
    """The scenario's project root and most recent command result."""

    root: pathlib.Path
    last_run: CapturedProcess


def _root(state: RuleDiscoveryState) -> pathlib.Path:
    """Return the scenario's disposable project root."""
    return state["root"]


def _run(state: RuleDiscoveryState, command_line: str) -> CapturedProcess:
    """Run the requested shell-style command line through the CLI module."""
    argv = command_line.split()
    assert argv, "expected a nonempty command line"
    assert argv[0] == "stilyagi", (
        "expected every scenario command to spell the stilyagi program"
    )
    completed = run_python_module(_root(state), *argv[1:])
    state["last_run"] = completed
    return completed


def _last_run(state: RuleDiscoveryState) -> CapturedProcess:
    """Return the scenario's most recent run after asserting it exists."""
    completed = state.get("last_run")
    assert completed is not None, "expected the scenario to run the CLI"
    return completed


@given(
    "a directory with malformed Stilyagi configuration",
    target_fixture="rule_discovery_state",
)
def a_directory_with_malformed_configuration(
    tmp_path: pathlib.Path,
) -> RuleDiscoveryState:
    """Prepare a project whose discovered configuration cannot be parsed."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    return {"root": tmp_path}


@given("the builtin rule catalogue", target_fixture="rule_discovery_state")
def the_builtin_rule_catalogue(tmp_path: pathlib.Path) -> RuleDiscoveryState:
    """Prepare an empty project for a catalogue query."""
    return {"root": tmp_path}


@given("the builtin TERM001 rule", target_fixture="rule_discovery_state")
def the_builtin_term001_rule(tmp_path: pathlib.Path) -> RuleDiscoveryState:
    """Prepare an empty project for a TERM001 detail query."""
    return {"root": tmp_path}


@when(parsers.parse('the maintainer runs "{command_line}"'))
def the_maintainer_runs(
    rule_discovery_state: RuleDiscoveryState,
    command_line: str,
) -> None:
    """Invoke the requested command in the scenario's project."""
    _run(rule_discovery_state, command_line)


@then("the command succeeds without reading configuration")
def the_command_succeeds_without_configuration(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Assert the command exits zero and writes nothing to standard error."""
    completed = _last_run(rule_discovery_state)
    assert completed.returncode == 0, "expected static discovery to succeed"
    assert not completed.stderr, "expected no failure output"


@then(parsers.parse('the ordered codes are "{codes}"'))
def the_ordered_codes_are(rule_discovery_state: RuleDiscoveryState, codes: str) -> None:
    """Assert the JSON list carries exactly the stated codes in order."""
    completed = _last_run(rule_discovery_state)
    payload = json.loads(completed.stdout)
    observed = [rule["code"] for rule in payload["rules"]]
    assert observed == codes.split(","), "expected the stated ordered codes"


@then("TERM001 is described as disabled by default")
def term001_is_disabled_by_default(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Assert the opt-in rule reports that the default selection excludes it."""
    completed = _last_run(rule_discovery_state)
    payload = json.loads(completed.stdout)
    term = next(rule for rule in payload["rules"] if rule["code"] == "TERM001")
    assert term["enabled_by_default"] is False, "expected an opt-in rule"


@then("both case_sensitive boolean variants are explained")
def both_boolean_variants_are_explained(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Assert the text detail documents both boolean variants and their consequences."""
    detail = _last_run(rule_discovery_state).stdout.decode("utf-8")
    assert "false:" in detail, "expected the false variant"
    assert "true:" in detail, "expected the true variant"
    assert "casefold" in detail, "expected the folded comparison"
    assert "exact" in detail, "expected the exact comparison"


@then("the enablement example selects TERM001 and supplies terms")
def the_enablement_example_is_configuration(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Assert the printed TOML selects the rule and supplies a nonempty term list."""
    detail = _last_run(rule_discovery_state).stdout.decode("utf-8")
    documented = get_rule("TERM001").description.configuration.toml
    assert 'select = ["MD", "STY", "TERM001"]' in documented, (
        "expected the example to select TERM001"
    )
    assert 'terms = ["obviously"]' in documented, "expected the example to supply terms"
    assert documented.strip().splitlines()[-1] in detail, (
        "expected the detail to print the documented TOML"
    )


@then("the documented example produces its expected finding")
def the_documented_example_runs(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Run the printed TOML and example source through `check`."""
    root = _root(rule_discovery_state)
    description = get_rule("TERM001").description
    example = next(item for item in description.examples if item.expected_codes)
    (root / "pyproject.toml").write_text(
        description.configuration.toml,
        encoding="utf-8",
    )
    (root / "example.md").write_text(example.source, encoding="utf-8")

    completed = run_python_module(root, "check", "example.md")

    assert completed.returncode == 1, "expected the documented finding to fail check"
    for code in example.expected_codes:
        assert code.encode() in completed.stdout, (
            f"expected the documented example to report {code}"
        )


@then("only STY001 is listed")
def only_sty001_is_listed(rule_discovery_state: RuleDiscoveryState) -> None:
    """Assert the fixability filter selects the one rule that can propose an edit."""
    completed = _last_run(rule_discovery_state)
    rows = completed.stdout.decode("utf-8").splitlines()[1:]
    assert [row.split()[0] for row in rows] == ["STY001"], (
        "expected only the unsafe-edit rule to be fixable"
    )


@then("its fix mode is unsafe")
def its_fix_mode_is_unsafe(rule_discovery_state: RuleDiscoveryState) -> None:
    """Assert the listed row reports the unsafe fix mode."""
    completed = _last_run(rule_discovery_state)
    row = completed.stdout.decode("utf-8").splitlines()[1]
    assert row.split()[3] == "unsafe", "expected the unsafe fix mode column"


@then("the exit status is 2")
def the_exit_status_is_two(rule_discovery_state: RuleDiscoveryState) -> None:
    """Assert the failed lookup uses the operational-failure status."""
    assert _last_run(rule_discovery_state).returncode == 2, (
        "expected the documented operational-failure status"
    )


@then("standard output is empty")
def standard_output_is_empty(rule_discovery_state: RuleDiscoveryState) -> None:
    """Assert a failed lookup emits no machine-readable result."""
    assert not _last_run(rule_discovery_state).stdout, "expected empty standard output"


@then("standard error identifies the unknown code")
def standard_error_identifies_the_code(
    rule_discovery_state: RuleDiscoveryState,
) -> None:
    """Assert the failure names the code the maintainer requested."""
    error = _last_run(rule_discovery_state).stderr.decode("utf-8")
    assert "unknown rule code" in error, "expected an actionable failure"
    assert "UNKNOWN" in error, "expected the requested code in the message"
