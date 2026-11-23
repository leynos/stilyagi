"""Prove the catalogue's claims against the real parser and rule engine.

Every documented TOML example is parsed by the production configuration
pipeline, and every documented source example is linted by the production rule
engine. A default, a typed option, an example, and a boolean variant are each
checked against observable behaviour rather than against a second projection of
the same record.

The three-rule expected table here is written by hand. Comparing two views of
one metadata record would agree with itself no matter what the record said.
"""

import typing as typ

import pytest
from stilyagi import config
from stilyagi.check_outcome import compute_exit_code
from stilyagi.config.rules import Term001Config, parse_term001
from stilyagi.rules import catalogue
from stilyagi.rules.builtin import enabled_codes

from tests.support.rule_contract_support import lint, resolved_config

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.rules.base import RuleMetadata
    from stilyagi.rules.description import RuleExample

_DEFAULT_SELECT = ("MD", "DOC", "PUN", "STY", "PYDOC")


def _documented_examples() -> tuple[tuple[RuleMetadata, RuleExample], ...]:
    """Return every documented example paired with its rule."""
    return tuple(
        (rule, example)
        for rule in catalogue.list_rules()
        for example in rule.description.examples
    )


def _example_id(item: tuple[RuleMetadata, RuleExample]) -> str:
    """Name one example by rule code and title for pytest output."""
    rule, example = item
    return f"{rule.code}:{example.title}"


@pytest.mark.parametrize("item", _documented_examples(), ids=_example_id)
def test_documented_example_produces_its_expected_codes(
    item: tuple[RuleMetadata, RuleExample],
    tmp_path: pathlib.Path,
) -> None:
    """Every documented example is executable and yields the stated findings.

    The example's own TOML, when present, is parsed by the real configuration
    pipeline, so a documented key the parser rejects fails here rather than in
    a user's repository.
    """
    rule, example = item
    effective = (
        resolved_config(tmp_path, example.configuration)
        if example.configuration
        else config.StilyagiConfig()
    )

    produced = lint(effective, example.source)

    assert tuple(finding.code for finding in produced) == example.expected_codes, (
        f"expected {rule.code}'s documented example to produce its stated codes"
    )
    assert type(example.exit_code) is int, (
        "expected the authored exit status to be an integer, not a bool or float"
    )
    assert compute_exit_code(produced) == example.exit_code, (
        "expected the documented exit status to follow the real severity policy"
    )


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_published_configuration_parses_through_the_real_pipeline(
    rule: RuleMetadata,
    tmp_path: pathlib.Path,
) -> None:
    """Every rule publishes configuration the real parser accepts.

    The rendered `configuration.toml` is what a maintainer copies out of the
    catalogue, so it must parse as written. The example loop covers the TOML an
    example carries; this covers the separately published guidance, including
    the MD001 and STY001 snippets that no example repeats.
    """
    published = rule.description.configuration.toml
    assert published, f"expected {rule.code} to publish configuration guidance"

    effective = resolved_config(tmp_path, published)

    assert effective.lint.select, "expected the published TOML to select a rule"


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_published_configuration_lints_its_rule(
    rule: RuleMetadata,
    tmp_path: pathlib.Path,
) -> None:
    """The published TOML enables the rule whose description prints it.

    A code prefix would satisfy a weaker check, so this asserts the rule is
    actually enabled by the real policy for a document, not merely mentioned.
    """
    effective = resolved_config(tmp_path, rule.description.configuration.toml)
    reporting_example = next(
        (
            example
            for example in rule.description.examples
            if rule.code in example.expected_codes
        ),
        None,
    )
    assert reporting_example is not None, f"expected {rule.code} to document a finding"

    produced = lint(effective, reporting_example.source)

    assert rule.code in {item.code for item in produced}, (
        "expected the published TOML to enable the rule it documents"
    )


def test_default_selection_enables_md_and_sty_but_not_term() -> None:
    """The shipped default selection explains TERM001's disabled-by-default flag."""
    default_config = config.StilyagiConfig()
    default_select = default_config.lint.select

    assert default_select == _DEFAULT_SELECT, (
        "expected the documented default lint selection"
    )
    selected = {
        code for code in enabled_codes() if code.startswith(tuple(default_select))
    }
    assert selected == {"MD001", "STY001"}, (
        "expected MD and STY to be enabled by default and TERM to be opt-in"
    )


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_enabled_by_default_agrees_with_selection(rule: RuleMetadata) -> None:
    """Every descriptor's default-enablement flag matches real selection."""
    selected = {
        code
        for code in enabled_codes()
        if code.startswith(tuple(config.StilyagiConfig().lint.select))
    }

    assert rule.description.enabled_by_default is (rule.code in selected), (
        "expected the catalogue's default-enablement claim to match policy"
    )


def test_term001_is_inactive_without_terms() -> None:
    """Selecting TERM001 alone reports nothing until terms are configured."""
    effective = config.StilyagiConfig(
        lint=config.LintConfig(select=("TERM001",)),
    )

    assert lint(effective, "This is obviously fine.\n") == [], (
        "expected an empty term list to keep TERM001 inactive"
    )


@pytest.mark.parametrize(
    ("toml_text", "expected"),
    [
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterms = ["obviously"]\n',
            Term001Config(terms=("obviously",), case_sensitive=False),
            id="case-insensitive-default",
        ),
        pytest.param(
            "[tool.stilyagi.rule.TERM001]\n"
            'terms = ["Obviously", "obviously"]\n'
            "case_sensitive = false\n",
            Term001Config(terms=("obviously",), case_sensitive=False),
            id="coalesced-under-folding",
        ),
        pytest.param(
            "[tool.stilyagi.rule.TERM001]\n"
            'terms = ["Obviously", "obviously"]\n'
            "case_sensitive = true\n",
            Term001Config(terms=("Obviously", "obviously"), case_sensitive=True),
            id="distinct-under-exact-case",
        ),
        pytest.param(
            "[tool.stilyagi.rule.TERM001]\nterms = []\n",
            Term001Config(),
            id="empty-terms",
        ),
    ],
)
def test_documented_term_defaults_match_the_real_parser(
    toml_text: str,
    expected: Term001Config,
    tmp_path: pathlib.Path,
) -> None:
    """The documented `terms`/`case_sensitive` defaults are the parser's."""
    effective = resolved_config(tmp_path, toml_text)
    table = effective.rules["TERM001"]

    assert parse_term001(table, "TERM001") == expected, (
        "expected the documented option defaults to match the real parser"
    )


@pytest.mark.parametrize(
    ("toml_text", "offending_key"),
    [
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterms = ["two words"]\n',
            "terms[0]",
            id="space",
        ),
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterms = ["word."]\n',
            "terms[0]",
            id="punctuation",
        ),
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterms = ["word2"]\n',
            "terms[0]",
            id="digit",
        ),
        pytest.param(
            "[tool.stilyagi.rule.TERM001]\nterms = [1]\n",
            "terms[0]",
            id="not-a-string",
        ),
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterms = "obviously"\n',
            "terms",
            id="not-a-list",
        ),
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\ncase_sensitive = "yes"\n',
            "case_sensitive",
            id="not-a-boolean",
        ),
        pytest.param(
            '[tool.stilyagi.rule.TERM001]\nterm = ["obviously"]\n',
            "term",
            id="unknown-key",
        ),
    ],
)
def test_documented_constraints_are_parser_enforced(
    toml_text: str,
    offending_key: str,
    tmp_path: pathlib.Path,
) -> None:
    """Each documented rejection is enforced by the real configuration parser."""
    effective = resolved_config(tmp_path, toml_text)

    with pytest.raises(config.InvalidConfigError) as raised:
        parse_term001(effective.rules["TERM001"], "TERM001")

    assert offending_key in str(raised.value), (
        "expected the parser to name the documented offending key"
    )


def test_documented_boolean_variants_are_observable() -> None:
    """Both documented `case_sensitive` variants match their descriptions."""
    insensitive = config.StilyagiConfig(
        lint=config.LintConfig(select=("TERM001",)),
        rules={"TERM001": {"terms": ["obviously"], "case_sensitive": False}},
    )
    sensitive = config.StilyagiConfig(
        lint=config.LintConfig(select=("TERM001",)),
        rules={"TERM001": {"terms": ["obviously"], "case_sensitive": True}},
    )

    assert [item.code for item in lint(insensitive, "Obviously fine.\n")] == [
        "TERM001"
    ], "expected the default variant to fold case"
    assert lint(sensitive, "Obviously fine.\n") == [], (
        "expected the exact-case variant to reject the folded spelling"
    )
    assert [item.code for item in lint(sensitive, "obviously fine.\n")] == [
        "TERM001"
    ], "expected the exact-case variant to match the exact spelling"


def test_documented_unicode_folding_is_observable() -> None:
    """A documented Unicode term matches through `casefold`, as described."""
    effective = config.StilyagiConfig(
        lint=config.LintConfig(select=("TERM001",)),
        rules={"TERM001": {"terms": ["straße"]}},
    )

    assert [item.code for item in lint(effective, "STRASSE matters.\n")] == [
        "TERM001"
    ], "expected `straße` to match `STRASSE` under case folding"
