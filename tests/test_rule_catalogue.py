"""Inventory, lookup, and filter coverage for the builtin rule catalogue.

The catalogue is a static query over the shipped builtin declarations, so these
tests describe it without a document, a configuration file, or a command. The
expectations are an independent table of the three shipped rules, not a second
projection of the same metadata: a change to a rule's severity, fix mode, or
default enablement has to be argued for here as well as in the declaration.
"""

import dataclasses as dc
import functools
import typing as typ

import pytest
from stilyagi.rules import catalogue
from stilyagi.rules.base import RuleMetadata
from stilyagi.rules.catalogue import RuleFilters
from stilyagi.rules.registry import builtin_metadata

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@dc.dataclass(frozen=True, slots=True)
class ExpectedRule:
    """The shipped contract for one rule, stated independently of the metadata."""

    code: str
    name: str
    severity: str
    fix_mode: str
    fixable: bool
    enabled_by_default: bool
    preview: bool
    requires: tuple[str, ...]
    option_names: tuple[str, ...]


EXPECTED_RULES: typ.Final[tuple[ExpectedRule, ...]] = (
    ExpectedRule(
        code="MD001",
        name="heading-depth",
        severity="error",
        fix_mode="manual",
        fixable=False,
        enabled_by_default=True,
        preview=False,
        requires=("STRUCTURE",),
        option_names=(),
    ),
    ExpectedRule(
        code="STY001",
        name="repeated-word",
        severity="warning",
        fix_mode="unsafe",
        fixable=True,
        enabled_by_default=True,
        preview=False,
        requires=("STRUCTURE", "TOKENS"),
        option_names=(),
    ),
    ExpectedRule(
        code="TERM001",
        name="banned-term",
        severity="error",
        fix_mode="none",
        fixable=False,
        enabled_by_default=False,
        preview=False,
        requires=("STRUCTURE", "TOKENS"),
        option_names=("terms", "case_sensitive"),
    ),
)


def _expected(code: str) -> ExpectedRule:
    """Return the independent expectation for one shipped code."""
    return next(rule for rule in EXPECTED_RULES if rule.code == code)


def test_catalogue_lists_every_shipped_rule_in_code_order() -> None:
    """The complete inventory is all three rules, sorted by code."""
    listed = catalogue.list_rules()

    assert [rule.code for rule in listed] == [rule.code for rule in EXPECTED_RULES], (
        "expected the complete shipped inventory in code order"
    )


@pytest.mark.parametrize("expected", EXPECTED_RULES, ids=lambda rule: rule.code)
def test_catalogue_descriptor_matches_the_shipped_contract(
    expected: ExpectedRule,
) -> None:
    """Each descriptor states the policy the rule actually applies."""
    rule = catalogue.get_rule(expected.code)
    description = rule.description

    assert rule.name == expected.name, "expected the documented rule name"
    assert rule.default_severity == expected.severity, (
        "expected the documented default severity"
    )
    assert rule.pack == "builtin", "expected every shipped rule in the builtin pack"
    assert description.fix_mode == expected.fix_mode, "expected the documented fix mode"
    assert description.fixable is expected.fixable, (
        "expected fixability to follow the fix mode"
    )
    assert description.enabled_by_default is expected.enabled_by_default, (
        "expected the documented default enablement"
    )
    assert description.preview is expected.preview, (
        "expected every shipped rule to be non-preview"
    )
    assert description.requires == expected.requires, (
        "expected the RFC 0002 capability declaration"
    )
    assert rule.requires_nlp is False, "expected no shipped rule to need NLP"
    assert (
        tuple(option.name for option in description.configuration.options)
        == expected.option_names
    ), "expected the documented typed options"


@pytest.mark.parametrize(
    "code",
    [pytest.param("MD001", id="md001"), pytest.param("TERM001", id="term001")],
)
def test_catalogue_lookup_returns_the_inventory_descriptor(code: str) -> None:
    """Lookup returns the very object the inventory holds, not a copy."""
    inventory = {rule.code: rule for rule in builtin_metadata()}

    assert catalogue.get_rule(code) is inventory[code], (
        "expected the catalogue to reuse the inventory descriptor"
    )


@pytest.mark.parametrize(
    "code",
    [
        pytest.param("UNKNOWN", id="unknown"),
        pytest.param("md001", id="lower-case"),
        pytest.param("MD", id="prefix"),
        pytest.param("MD0010", id="longer"),
        pytest.param("", id="empty"),
    ],
)
def test_catalogue_lookup_rejects_anything_but_an_exact_code(code: str) -> None:
    """An unknown, lower-case, or prefix spelling is a named miss."""
    with pytest.raises(catalogue.RuleNotFoundError) as raised:
        catalogue.get_rule(code)

    assert raised.value.code == code, "expected the miss to retain the requested code"
    assert code in str(raised.value), "expected the message to name the code"


def test_catalogue_lookup_error_is_a_lookup_error() -> None:
    """The miss is a `LookupError`, so callers can catch it generically."""
    with pytest.raises(LookupError):
        catalogue.get_rule("NOPE")


@pytest.mark.parametrize(
    ("filters", "expected_codes"),
    [
        pytest.param(RuleFilters(), ["MD001", "STY001", "TERM001"], id="no-filters"),
        pytest.param(RuleFilters(prefix="MD"), ["MD001"], id="prefix-md"),
        pytest.param(RuleFilters(prefix="S"), ["STY001"], id="prefix-single-letter"),
        pytest.param(RuleFilters(prefix="TERM"), ["TERM001"], id="prefix-term"),
        pytest.param(RuleFilters(prefix="md"), [], id="prefix-case-sensitive"),
        pytest.param(RuleFilters(prefix="ZZ"), [], id="prefix-unknown"),
        pytest.param(
            RuleFilters(pack="builtin"), ["MD001", "STY001", "TERM001"], id="pack-known"
        ),
        pytest.param(RuleFilters(pack="plugin"), [], id="pack-unknown"),
        pytest.param(RuleFilters(severity="error"), ["MD001", "TERM001"], id="error"),
        pytest.param(RuleFilters(severity="warning"), ["STY001"], id="warning"),
        pytest.param(RuleFilters(severity="info"), [], id="info-none"),
        pytest.param(RuleFilters(preview=True), [], id="preview-yes-none"),
        pytest.param(
            RuleFilters(preview=False),
            ["MD001", "STY001", "TERM001"],
            id="preview-no-all",
        ),
        pytest.param(RuleFilters(fixable=True), ["STY001"], id="fixable-yes"),
        pytest.param(
            RuleFilters(fixable=False),
            ["MD001", "TERM001"],
            id="fixable-no-includes-manual",
        ),
        pytest.param(
            RuleFilters(prefix="TERM", severity="warning"),
            [],
            id="conjunction-empty",
        ),
        pytest.param(
            RuleFilters(prefix="MD", severity="error"),
            ["MD001"],
            id="conjunction-matching",
        ),
    ],
)
def test_catalogue_filters_select_the_documented_set(
    filters: RuleFilters,
    expected_codes: list[str],
) -> None:
    """Every filter dimension and their conjunction select the stated rules."""
    assert [rule.code for rule in catalogue.list_rules(filters)] == expected_codes, (
        "expected the documented filtering result"
    )


def test_catalogue_queries_leave_the_inventory_unchanged() -> None:
    """A query never mutates the shared descriptors or their order."""
    before = builtin_metadata()

    catalogue.list_rules(RuleFilters(prefix="TERM"))
    catalogue.get_rule("MD001")

    assert builtin_metadata() == before, "expected the inventory to be unchanged"
    assert [rule.code for rule in builtin_metadata()] == [
        "MD001",
        "STY001",
        "TERM001",
    ], "expected the inventory order to be unchanged"


@pytest.mark.parametrize(
    ("make_filters", "message"),
    [
        pytest.param(
            functools.partial(RuleFilters, prefix=""),
            "prefix",
            id="empty-prefix",
        ),
        pytest.param(
            functools.partial(RuleFilters, pack=""),
            "pack",
            id="empty-pack",
        ),
        pytest.param(
            functools.partial(RuleFilters, severity="fatal"),
            "severity",
            id="bad-severity",
        ),
    ],
)
def test_catalogue_rejects_unusable_filter_values(
    make_filters: cabc.Callable[[], RuleFilters],
    message: str,
) -> None:
    """A filter the query cannot honour is rejected at construction."""
    with pytest.raises(ValueError, match=message):
        make_filters()


def test_catalogue_filters_are_immutable() -> None:
    """A filter record cannot be changed after construction."""
    filters = RuleFilters(prefix="MD")

    with pytest.raises(dc.FrozenInstanceError):
        # Calling the generated setter is the subject: it must reject the write.
        RuleFilters.__setattr__(filters, "prefix", "STY")


def test_catalogue_descriptors_are_immutable() -> None:
    """A descriptor cannot be changed after construction."""
    rule: RuleMetadata = catalogue.get_rule("MD001")

    with pytest.raises(dc.FrozenInstanceError):
        # Calling the generated setter is the subject: it must reject the write.
        RuleMetadata.__setattr__(rule, "default_severity", "warning")
