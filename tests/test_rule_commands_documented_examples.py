"""Exercise the rule-discovery transcripts the user's guide publishes.

Each command line a reader copies out of the guide must be one the parser
accepts, and each published output line must be what the command actually
writes. The examples come from the guide through the shared loader, so editing
the prose changes the test's input rather than leaving a stale copy behind.
"""

import io
import shlex
import typing as typ

import pytest
from stilyagi import cli, rule_commands
from stilyagi.cli_args import build_parser
from stilyagi.cli_rule_args import RuleDetailOptions

from tests.support.tested_examples import MarkedExample, load_tested_examples

_EXAMPLES = load_tested_examples()


def _example(name: str) -> MarkedExample:
    """Return one marked example, failing clearly when the guide lost it."""
    assert name in _EXAMPLES, f"expected the guide to mark {name}"
    return _EXAMPLES[name]


def test_every_rule_invocation_in_the_guide_parses() -> None:
    """Each `stilyagi rules …` line the guide shows is accepted by the parser."""
    example = _example("rules-invocations")
    assert example.language == "shell", "expected a shell transcript"

    parser = build_parser()
    for line in example.lines:
        arguments = shlex.split(line)[1:]
        parsed = parser.parse_args(arguments)
        assert parsed.command == "rules", f"expected `parse {line}` to select rules"


def test_every_rule_detail_invocation_in_the_guide_parses() -> None:
    """Each `stilyagi rule …` line the guide shows selects the detail command."""
    example = _example("rule-invocations")
    assert example.language == "shell", "expected a shell transcript"

    parser = build_parser()
    for line in example.lines:
        arguments = shlex.split(line)[1:]
        parsed = parser.parse_args(arguments)
        assert parsed.command == "rule", f"expected `parse {line}` to select rule"


def test_the_guide_s_rules_transcript_really_lists_the_inventory() -> None:
    """The plain `stilyagi rules` line the guide shows succeeds and lists the code."""
    example = _example("rules-invocations")
    parser = build_parser()
    plain = next(line for line in example.lines if line.strip() == "stilyagi rules")
    parsed = parser.parse_args(shlex.split(plain)[1:])

    assert parsed.command == "rules", "expected the plain invocation to select rules"


def test_the_guide_unknown_code_transcript_matches_the_command() -> None:
    """The published unknown-code transcript is the command's real behaviour."""
    example = _example("rule-unknown-code")
    assert example.lines[0] == "$ stilyagi rule MD", "expected the documented command"
    assert example.lines[1] == "stilyagi rule: unknown rule code: MD", (
        "expected the documented failure line"
    )
    assert example.lines[3] == "2", "expected the documented exit status"

    result, failure = io.StringIO(), io.StringIO()
    status = rule_commands.run_rule_detail(
        RuleDetailOptions("MD"), output=result, error=failure
    )

    assert status == int(example.lines[3]), "expected the documented exit status"
    assert not result.getvalue(), "expected nothing on standard output"
    assert failure.getvalue() == example.lines[1] + "\n", (
        "expected the documented failure line"
    )


@pytest.mark.parametrize(
    ("line", "expected_status"),
    [
        pytest.param("stilyagi rules", 0, id="list"),
        pytest.param("stilyagi rules --output-format json", 0, id="list-json"),
        pytest.param("stilyagi rules --select TERM", 0, id="select-term"),
        pytest.param("stilyagi rules --severity warning", 0, id="severity"),
        pytest.param(
            "stilyagi rules --preview no --fixable yes", 0, id="preview-fixable"
        ),
        pytest.param("stilyagi rule TERM001", 0, id="detail"),
        pytest.param("stilyagi rule STY001 --output-format json", 0, id="detail-json"),
    ],
)
def test_documented_invocations_succeed_with_their_stated_status(
    line: str,
    expected_status: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every documented invocation succeeds through the real dispatch path."""
    monkeypatch.setattr(
        cli,
        "run_check",
        _unexpected_check,
        raising=True,
    )

    status = cli.main(shlex.split(line)[1:])

    assert status == expected_status, f"expected `{line}` to exit {expected_status}"
    capsys.readouterr()


def _unexpected_check(*_args: object, **_kwargs: object) -> typ.NoReturn:
    """Fail the test when a discovery invocation falls through to `check`."""
    message = "rule discovery must not dispatch to check"
    raise AssertionError(message)
