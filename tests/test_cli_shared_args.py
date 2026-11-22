"""Shared argparse builders' validation behaviour.

Both the check command and the read-only everything-else commands accept the
same `--output-format` and rule-code flags. These tests pin the shared
builders' rejection paths, so a command that documents `text|json` cannot
quietly accept an unsupported format or an empty code list through the shared
shape.
"""

import argparse

import pytest
from stilyagi.cli_shared_args import (
    add_output_format_argument,
    add_rule_code_argument,
    flatten_rule_codes,
)


def _parser() -> argparse.ArgumentParser:
    """Return a parser carrying the shared format and rule-code arguments."""
    parser = argparse.ArgumentParser()
    add_output_format_argument(parser, help_text="select a format")
    add_rule_code_argument(parser, "--select", "select rule codes")
    return parser


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param("sarif", "planned for a later slice", id="sarif"),
        pytest.param("yaml", "invalid output format", id="unknown"),
        pytest.param("", "invalid output format", id="empty"),
    ],
)
def test_output_format_rejects_unsupported_values(
    value: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unsupported format is a usage error naming the supported set."""
    with pytest.raises(SystemExit) as raised:
        _parser().parse_args(["--output-format", value])

    assert raised.value.code == 2, "expected argparse's usage status"
    assert message in capsys.readouterr().err, "expected the reason on stderr"


@pytest.mark.parametrize(
    "value",
    [pytest.param("", id="empty"), pytest.param(", ,", id="blank-items")],
)
def test_rule_codes_require_at_least_one_code(value: str) -> None:
    """An empty comma-delimited list is rejected rather than selecting nothing."""
    with pytest.raises(SystemExit) as raised:
        _parser().parse_args(["--select", value])

    assert raised.value.code == 2, "expected argparse's usage status"


def test_rule_codes_split_and_flatten() -> None:
    """Repeated comma-delimited flags flatten in the order they were given."""
    parsed = _parser().parse_args(["--select", "MD,STY", "--select", "TERM001"])

    assert parsed.select == [("MD", "STY"), ("TERM001",)], (
        "expected argparse to keep the per-occurrence groups"
    )
    assert flatten_rule_codes(parsed.select) == ("MD", "STY", "TERM001"), (
        "expected the groups to flatten in order"
    )
