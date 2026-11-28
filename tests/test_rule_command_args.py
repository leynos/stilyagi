"""Parser coverage for the `stilyagi rule` and `stilyagi rules` commands.

These tests stop at the parsed option records: they assert defaults, every
filter dimension, argparse store semantics for repeated flags, and the usage
status for invalid values. Command behaviour and rendering live in
``test_rule_commands.py``.
"""

import pytest
from stilyagi import cli
from stilyagi.cli_rule_args import (
    RuleDetailOptions,
    rule_options_from_args,
    rules_options_from_args,
)
from stilyagi.rules.catalogue import RuleFilters


def test_rules_parser_defaults_to_text_and_no_filters() -> None:
    """An unadorned `rules` invocation selects the whole inventory as text."""
    options = rules_options_from_args(cli.build_parser().parse_args(["rules"]))

    assert options.output_format == "text", "expected text output by default"
    assert options.filters == RuleFilters(), "expected no filter by default"


def test_rules_parser_collects_every_filter() -> None:
    """Every documented filter reaches the immutable options record."""
    parsed = cli.build_parser().parse_args([
        "rules",
        "--select",
        "TERM",
        "--pack",
        "builtin",
        "--severity",
        "error",
        "--preview",
        "no",
        "--fixable",
        "yes",
        "--output-format",
        "json",
    ])

    options = rules_options_from_args(parsed)

    assert options.filters == RuleFilters(
        prefix="TERM",
        pack="builtin",
        severity="error",
        preview=False,
        fixable=True,
    ), "expected every filter dimension to survive parsing"
    assert options.output_format == "json", "expected JSON output"


def test_rules_parser_uses_the_last_repeated_filter_value() -> None:
    """A repeated single-valued filter follows argparse store semantics."""
    parsed = cli.build_parser().parse_args([
        "rules",
        "--select",
        "MD",
        "--select",
        "STY",
        "--fixable",
        "yes",
        "--fixable",
        "no",
    ])

    options = rules_options_from_args(parsed)

    assert options.filters.prefix == "STY", "expected the last prefix to win"
    assert options.filters.fixable is False, "expected the last fixable value to win"


def test_rule_parser_collects_the_code_and_format() -> None:
    """The detail command keeps its exact code and chosen format."""
    options = rule_options_from_args(
        cli.build_parser().parse_args(["rule", "TERM001", "--output-format", "json"])
    )

    assert options == RuleDetailOptions(code="TERM001", output_format="json"), (
        "expected the detail options to preserve the code and format"
    )


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["rules", "--select", ""], id="empty-prefix"),
        pytest.param(["rules", "--pack", ""], id="empty-pack"),
        pytest.param(["rules", "--severity", "fatal"], id="bad-severity"),
        pytest.param(["rules", "--preview", "maybe"], id="bad-preview"),
        pytest.param(["rules", "--fixable", "maybe"], id="bad-fixable"),
        pytest.param(["rules", "--output-format", "yaml"], id="bad-format"),
        pytest.param(["rule"], id="missing-code"),
        pytest.param(["rule", "MD001", "STY001"], id="two-codes"),
        pytest.param(
            ["rule", "MD001", "--output-format", "sarif"], id="bad-rule-format"
        ),
    ],
)
def test_invalid_arguments_exit_two_with_empty_stdout(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The parser owns invalid arguments: status two, stderr only."""
    assert cli.main(argv) == 2, "expected the parser's usage status"
    captured = capsys.readouterr()
    assert not captured.out, "expected no partial result on standard output"
    assert captured.err, "expected the usage message on standard error"
