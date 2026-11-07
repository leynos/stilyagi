"""Malformed builtin-rule option tables are rejected at the config boundary.

``validate_builtin_tables`` and ``parse_term001`` turn a raw
``[tool.stilyagi.rule.CODE]`` mapping into a validated frozen record. These
tests hold the rejection branches: an unknown option on a rule that takes none,
a term list of the wrong shape, a term that is not a string, a mistyped flag,
and duplicate terms coalescing rather than repeating.
"""

import pathlib

import pytest
from stilyagi import config
from stilyagi.config import rules as rule_options

_CONFIG_PATH = pathlib.Path("stilyagi.toml")


def _term001(table: dict[str, object]) -> rule_options.Term001Config:
    """Parse one raw ``TERM001`` table against a fixed config path."""
    return rule_options.parse_term001(table, "TERM001", _CONFIG_PATH)


def test_an_unknown_option_on_an_optionless_rule_is_rejected() -> None:
    """A misspelled key fails even though ``MD001`` takes no options."""
    effective = config.StilyagiConfig(rules={"MD001": {"depth": 2}})

    with pytest.raises(config.InvalidConfigError) as caught:
        rule_options.validate_builtin_tables(effective, path=_CONFIG_PATH)

    assert caught.value.key == "rule.MD001.depth", "expected the offending key"
    assert caught.value.detail == "is not supported", "expected the rejection reason"


@pytest.mark.parametrize(
    ("table", "key", "detail"),
    [
        pytest.param(
            {"terms": "obviously"},
            "rule.TERM001.terms",
            "must be a list of strings",
            id="terms-not-a-list",
        ),
        pytest.param(
            {"terms": [1]},
            "rule.TERM001.terms[0]",
            "must be a string",
            id="term-not-a-string",
        ),
        pytest.param(
            {"terms": ["obviously"], "case_sensitive": "yes"},
            "rule.TERM001.case_sensitive",
            "must be a boolean",
            id="flag-not-a-boolean",
        ),
    ],
)
def test_a_malformed_term_table_names_the_offending_key(
    table: dict[str, object], key: str, detail: str
) -> None:
    """Each malformed value is refused with its own key and reason."""
    with pytest.raises(config.InvalidConfigError) as caught:
        _term001(table)

    assert caught.value.key == key, "expected the offending key"
    assert caught.value.detail == detail, "expected the rejection reason"


def test_duplicate_terms_coalesce_after_normalization() -> None:
    """Case-insensitive duplicates become one comparison term."""
    parsed = _term001({"terms": ["Obviously", "obviously"]})

    assert parsed.terms == ("obviously",), "expected one normalized term"
