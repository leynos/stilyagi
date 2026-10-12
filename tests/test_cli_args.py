"""Argument-parser coverage for the `check` command's options.

These tests exercise `build_parser` and `options_from_args` directly, with no
`run_check` and no filesystem, so they say nothing about what a run does with
an option once it has been parsed.

The `--diff` switch is pinned here too, but its *behaviour* -- the preview, the
three empty-patch cases, and the rendering counters -- lives in
`tests/test_check_diff.py`. Three of the pins below are regression tests for a
defect the parser carried silently: `default=()` with `action="append"` makes
argparse copy a tuple before appending to it, so the flag raised
`AttributeError` the first time it was passed. `--diff` could not catch that,
being a `store_true` flag with no default to copy.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_cli_args.py
"""

import pytest
from stilyagi import cli


def test_check_parser_sets_the_diff_option() -> None:
    """Expose the non-mutating preview switch through the check parser."""
    parsed = cli.build_parser().parse_args(["check", "--diff", "notes.md"])

    assert cli.CheckOptions(targets=("notes.md",), diff=True) == cli.options_from_args(
        parsed
    ), "expected --diff to populate the immutable check options"


@pytest.mark.parametrize(
    ("flag", "field", "codes"),
    [
        pytest.param("--select", "select", ("PUN201", "PUN202"), id="select"),
        pytest.param("--ignore", "ignore", ("PUN201",), id="ignore"),
        pytest.param(
            "--extend-select", "extend_select", ("PUN202",), id="extend-select"
        ),
    ],
)
def test_check_parser_accepts_repeatable_rule_code_arguments(
    flag: str, field: str, codes: tuple[str, ...]
) -> None:
    """Collect comma-delimited rule codes from a repeated selection flag.

    This is the regression pin for a defect the parser carried silently: the
    three selection flags declared `default=()` with `action="append"`, and
    argparse copies the default before appending to it. Copying a tuple yields
    a tuple, so every one of these flags raised `AttributeError` the first time
    it was actually passed. The existing `--diff` test could not catch it
    because `--diff` is a `store_true` flag with no default to copy, which is
    why the defect survived the flags being documented in the users' guide.

    Both halves are asserted: the flag parses at all, and the codes it selected
    reach the options object. A parser that swallowed the flag without raising
    would satisfy the first half alone.
    """
    parsed = cli.build_parser().parse_args(["check", flag, ",".join(codes), "notes.md"])

    options = cli.options_from_args(parsed)
    assert codes == getattr(options, field), (
        f"expected {flag} to populate CheckOptions.{field}"
    )


def test_check_parser_defaults_repeated_rule_code_arguments_to_empty() -> None:
    """Leave every selection field empty when no selection flag is passed."""
    options = cli.options_from_args(
        cli.build_parser().parse_args(["check", "notes.md"])
    )

    assert () == options.select == options.ignore == options.extend_select, (
        "expected the selection defaults to stay empty"
    )


def test_check_parser_collects_repeated_explicit_config_arguments() -> None:
    """Collect every explicit configuration source the user supplies.

    This is the same defect as the rule-code pin above, in the one argument the
    shared helper does not build. `--config` declared `default=()` with
    `action="append"`, so passing it raised `AttributeError: 'tuple' object has
    no attribute 'append'` -- the flag was unusable rather than merely
    mis-defaulted, and no test passed it. It is asserted separately from the
    selection flags because it is a separate `add_argument` call: fixing the
    helper does not fix this one, and the `default=[]` rationale has to be
    restated at the site that needs it.

    The value is a tuple on the options object even though the parser collects
    a list, because `options_from_args` normalises it. Both are pinned here.
    """
    parsed = cli.build_parser().parse_args([
        "check",
        "--config",
        "one.toml",
        "--config",
        "two.toml",
        "notes.md",
    ])

    options = cli.options_from_args(parsed)

    assert options.explicit_config == ("one.toml", "two.toml"), (
        "expected every --config value to reach CheckOptions.explicit_config"
    )


def test_check_parser_defaults_explicit_config_to_empty() -> None:
    """Leave the explicit configuration sources empty when none is passed."""
    options = cli.options_from_args(
        cli.build_parser().parse_args(["check", "notes.md"])
    )

    assert not options.explicit_config, (
        "expected no explicit configuration source by default"
    )
