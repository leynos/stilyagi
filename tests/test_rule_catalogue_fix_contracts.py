"""Executable contracts for fix claims, references, and capabilities.

The catalogue says a rule is manual, unsafe, or unfixable, names the
capabilities it needs, and cites repository documents. These tests check those
claims against the diagnostics the real engine emits and against the checkout
itself, so a decorative `fixable` flag or a stale reference fails here.
"""

import typing as typ

import pytest
from stilyagi import config
from stilyagi.config.rules import (
    Md001Config,
    Sty001Config,
    parse_optionless,
)
from stilyagi.fixes import Applicability
from stilyagi.rules import catalogue
from stilyagi.rules.registry import builtin_metadata

from tests.support.rule_contract_support import (
    REPOSITORY_ROOT,
    config_selecting,
    example_syntax,
    first_reporting_example,
    lint,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.rules.base import RuleMetadata


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_documented_fix_claims_match_emitted_diagnostics(rule: RuleMetadata) -> None:
    """The documented fix mode matches the fix a finding actually carries.

    A rule that documents ``manual`` or ``none`` must never emit an edit, and a
    rule that documents ``unsafe`` must emit exactly an unsafe edit. This is the
    contract that stops `fixable: true` from being a decorative flag.
    """
    example = first_reporting_example(rule)
    produced = lint(
        config_selecting(rule.code),
        example.source,
        example_syntax(rule),
    )
    finding = next(
        (item for item in produced if item.code == rule.code),
        None,
    )
    assert finding is not None, (
        f"expected the documented example to produce a {rule.code} finding"
    )

    match rule.description.fix_mode:
        case "none":
            assert finding.fix is None, "expected a 'none' fix mode to emit no fix"
        case "manual":
            assert finding.fix is not None, "expected a manual suggestion"
            assert finding.fix.applicability is Applicability.MANUAL, (
                "expected the manual suggestion to be marked manual"
            )
            assert finding.fix.edits == (), (
                "expected manual guidance to provide no editable range"
            )
        case "unsafe":
            assert finding.fix is not None, "expected an unsafe edit"
            assert finding.fix.applicability is Applicability.UNSAFE, (
                "expected the edit to be marked unsafe"
            )
            assert finding.fix.edits, "expected unsafe mode to provide an edit"
        case other:  # pragma: no cover - the literal type exhausts the choices
            pytest.fail(f"unexpected fix mode: {other}")


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_documented_references_exist(rule: RuleMetadata) -> None:
    """Every repository path a rule cites exists in the checkout."""
    paths = [
        reference
        for reference in rule.description.references
        if not reference.startswith(("http://", "https://"))
    ]
    assert paths, "expected at least one repository reference"

    missing = [
        path for path in paths if not (REPOSITORY_ROOT / path.split("#")[0]).is_file()
    ]
    assert not missing, f"expected every referenced path to exist: {missing}"


@pytest.mark.parametrize("rule", catalogue.list_rules(), ids=lambda rule: rule.code)
def test_documented_capabilities_match_the_rule_shape(rule: RuleMetadata) -> None:
    """A textual rule declares TOKENS; a structural-only rule does not."""
    codes = {metadata.code for metadata in builtin_metadata()}
    assert rule.code in codes, "expected the rule in the runtime inventory"

    textual = rule.target.matches_kind("paragraph")
    assert ("TOKENS" in rule.description.requires) is textual, (
        "expected the capability declaration to follow the rule's target"
    )
    assert "STRUCTURE" in rule.description.requires, (
        "expected every builtin rule to need the structural capability"
    )


_TABLE: cabc.Mapping[str, object] = {"unexpected": True}


@pytest.mark.parametrize(
    ("code", "config_type"),
    [
        pytest.param("MD001", Md001Config, id="md001"),
        pytest.param("STY001", Sty001Config, id="sty001"),
    ],
)
def test_documented_option_free_rules_are_parser_enforced(
    code: str,
    config_type: type,
) -> None:
    """An option on MD001 or STY001 is rejected, as the catalogue states."""
    with pytest.raises(config.InvalidConfigError) as raised:
        parse_optionless(_TABLE, code, config_type=config_type)

    assert code in str(raised.value), "expected the parser to name the rule"
