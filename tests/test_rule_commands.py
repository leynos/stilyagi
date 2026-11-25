"""In-process coverage for the `stilyagi rule` and `stilyagi rules` commands.

These tests drive the command adapters directly with injected streams. They
pin the filter parsing, both output formats, error ownership, and the preserved
`check` dispatch. Snapshots record the exact presentation, but every snapshot
is paired with a semantic assertion so an approved snapshot cannot make a
contradictory value pass unnoticed.

Snapshot coverage is stable output only: no paths, hostnames, versions,
timestamps, or terminal-dependent widths reach the rendered text.
"""

import json

import pytest
from stilyagi import cli
from stilyagi.rule_rendering import render_rule_detail, render_rule_list
from stilyagi.rules import catalogue
from stilyagi.rules.catalogue import RuleFilters

from tests.support.rule_command_support import detail_result, list_result

_SECTIONS = (
    "Summary:",
    "Explanation:",
    "Targets:",
    "Capabilities:",
    "Policy/enablement:",
    "Fixes:",
    "Options:",
    "Examples:",
    "Limitations:",
    "References:",
)
_DESCRIPTOR_KEYS = frozenset({
    "code",
    "name",
    "pack",
    "summary",
    "explanation",
    "default_severity",
    "targets",
    "requires",
    "requires_nlp",
    "fixable",
    "fix_mode",
    "fixes",
    "enabled_by_default",
    "preview",
    "configuration",
    "examples",
    "limitations",
    "references",
})
_CODES = ("DOC001", "DOC002", "DOC003", "MD001", "STY001", "TERM001")


def test_text_list_has_the_documented_header_and_rows() -> None:
    """The list uses stable columns and one row per shipped rule."""
    status, output, error = list_result()

    assert status == 0, "expected an unfiltered list to succeed"
    assert not error, "expected no failure output"
    lines = output.splitlines()
    assert lines[0].split() == [
        "CODE",
        "NAME",
        "SEVERITY",
        "FIX-MODE",
        "DEFAULT",
        "PREVIEW",
    ], "expected the documented header columns"
    assert [line.split()[0] for line in lines[1:]] == list(_CODES), (
        "expected one row per shipped rule in code order"
    )
    assert output.endswith("\n"), "expected a trailing newline"
    assert not output.endswith("\n\n"), "expected exactly one trailing newline"


def test_text_list_reports_an_empty_result_with_its_own_sentence() -> None:
    """An unmatched filter is success with the documented sentence."""
    status, output, error = list_result(filters=RuleFilters(prefix="ZZ"))

    assert status == 0, "expected an empty filtered result to succeed"
    assert output == "No builtin rules match the supplied filters.\n", (
        "expected the documented no-match sentence"
    )
    assert not error, "expected no failure output"


@pytest.mark.parametrize(
    ("filters", "present", "absent"),
    [
        pytest.param(
            RuleFilters(prefix="TERM"),
            ["TERM001"],
            ["MD001", "STY001"],
            id="prefix",
        ),
        pytest.param(
            RuleFilters(severity="warning"),
            ["DOC001", "DOC002", "DOC003", "STY001"],
            ["MD001", "TERM001"],
            id="severity",
        ),
        pytest.param(
            RuleFilters(fixable=True),
            ["STY001"],
            ["MD001", "TERM001"],
            id="fixable",
        ),
        pytest.param(
            RuleFilters(fixable=False),
            ["DOC001", "DOC002", "DOC003", "MD001", "TERM001"],
            ["STY001"],
            id="manual-is-not-fixable",
        ),
        pytest.param(
            RuleFilters(preview=False),
            ["DOC001", "DOC002", "DOC003", "MD001", "STY001", "TERM001"],
            [],
            id="preview-no",
        ),
        pytest.param(
            RuleFilters(preview=True),
            [],
            ["DOC001", "DOC002", "DOC003", "MD001", "STY001", "TERM001"],
            id="preview-yes",
        ),
        pytest.param(
            RuleFilters(pack="builtin"),
            ["DOC001", "DOC002", "DOC003", "MD001", "STY001", "TERM001"],
            [],
            id="pack",
        ),
        pytest.param(
            RuleFilters(pack="other"),
            [],
            ["MD001", "STY001", "TERM001"],
            id="no-pack",
        ),
    ],
)
def test_text_list_applies_each_filter(
    filters: RuleFilters,
    present: list[str],
    absent: list[str],
) -> None:
    """Each filter's presence or absence of a rule is observable."""
    status, output, error = list_result(filters=filters)

    assert status == 0, "expected filtering to succeed"
    assert not error, "expected no failure output"
    listed = {line.split()[0] for line in output.splitlines()[1:]}
    assert sorted(listed) == sorted(present), (
        "expected exactly the rules the filter admits"
    )
    assert listed.isdisjoint(absent), (
        "expected every rule the filter excludes to be absent"
    )


@pytest.mark.parametrize("code", _CODES)
def test_detail_text_states_the_top_level_values(code: str) -> None:
    """The detail's identity block reports the catalogue's actual values."""
    status, output, error = detail_result(code)

    assert status == 0, "expected a known code to succeed"
    assert not error, "expected no failure output"
    expected = _expected_top_level(code)
    assert output.splitlines()[0] == f"{code} {expected['name']}", (
        "expected the detail to begin with the code and name"
    )
    for label, value in expected.items():
        if label == "name":
            continue
        assert f"{label}: {value}" in output, f"expected the labelled {label} value"


def _expected_top_level(code: str) -> dict[str, str]:
    """Return the independent top-level expectations for one rule."""
    values = {
        "MD001": {
            "name": "heading-depth",
            "Default severity": "error",
            "Pack": "builtin",
            "Enabled by default": "yes",
            "Preview": "no",
            "Fixable": "no",
            "Fix mode": "manual",
        },
        "STY001": {
            "name": "repeated-word",
            "Default severity": "warning",
            "Pack": "builtin",
            "Enabled by default": "yes",
            "Preview": "no",
            "Fixable": "yes",
            "Fix mode": "unsafe",
        },
        "TERM001": {
            "name": "banned-term",
            "Default severity": "error",
            "Pack": "builtin",
            "Enabled by default": "no",
            "Preview": "no",
            "Fixable": "no",
            "Fix mode": "none",
        },
        "DOC001": _doc_expectation("summary-separation"),
        "DOC002": _doc_expectation("summary-punctuation"),
        "DOC003": _doc_expectation("owner-only-summary"),
    }
    return values[code]


def _doc_expectation(name: str) -> dict[str, str]:
    """Return the shared top-level expectations for one documentation rule."""
    return {
        "name": name,
        "Default severity": "warning",
        "Pack": "builtin",
        "Enabled by default": "no",
        "Preview": "no",
        "Fixable": "no",
        "Fix mode": "none",
    }


@pytest.mark.parametrize("code", _CODES)
def test_detail_text_keeps_every_required_section(code: str) -> None:
    """Every labelled section remains visible for every rule."""
    _status, output, _error = detail_result(code)

    for section in _SECTIONS:
        assert section in output, f"expected the {section} section"


@pytest.mark.parametrize("code", ["MD001", "STY001"])
def test_detail_text_renders_explicit_none_for_absent_content(code: str) -> None:
    """An empty section says ``None`` rather than disappearing."""
    _status, output, _error = detail_result(code)

    assert "Options:\n  None" in output, "expected explicit None for empty options"


def test_term001_detail_documents_both_boolean_variants() -> None:
    """The opt-in rule renders false and true with their consequences."""
    _status, output, _error = detail_result("TERM001")
    description = catalogue.get_rule("TERM001").description
    option = next(
        item
        for item in description.configuration.options
        if item.name == "case_sensitive"
    )
    rendered = [line.strip() for line in output.splitlines()]

    for variant in option.variants:
        expected = f"{str(variant.value).lower()}: {variant.description}"
        assert expected in rendered, f"expected the {variant.value} variant line"

    folded, exact = option.variants
    assert folded.value is False, "expected the false variant first"
    assert "casefold" in folded.description, (
        "expected the false variant to describe case folding"
    )
    assert exact.value is True, "expected the true variant second"
    assert "exact" in exact.description, (
        "expected the true variant to describe exact spelling"
    )


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_unknown_code_reports_on_stderr_and_leaves_stdout_empty(
    output_format: str,
) -> None:
    """An unknown code is an operational error even when JSON was requested."""
    status, output, error = detail_result("UNKNOWN", output_format)

    assert status == 2, "expected the documented operational-failure status"
    assert not output, "expected no partial machine-readable output"
    assert error == "stilyagi rule: unknown rule code: UNKNOWN\n", (
        "expected one actionable failure line naming the code"
    )


def test_unknown_code_control_characters_stay_on_one_line() -> None:
    """The command escapes a newline so one failure cannot become two lines.

    The catalogue keeps the raw code, so this adapter is where the one-line
    guarantee is established and therefore where it is asserted.
    """
    status, output, error = detail_result("BAD\nCODE")

    assert status == 2, "expected the documented operational-failure status"
    assert not output, "expected no result for a miss"
    assert error.count("\n") == 1, "expected exactly one stderr line"
    assert "BAD\\nCODE" in error, "expected the newline to be escaped"


def test_json_list_envelope_and_descriptor_shape() -> None:
    """The list envelope is schema version 1 with complete typed descriptors."""
    status, output, error = list_result(output_format="json")

    assert status == 0, "expected the JSON list to succeed"
    assert not error, "expected no failure output"
    payload = json.loads(output)
    assert set(payload) == {"schema_version", "rules"}, (
        "expected only the documented envelope keys"
    )
    assert payload["schema_version"] == 1, "expected schema version 1"
    assert [rule["code"] for rule in payload["rules"]] == list(_CODES), (
        "expected the six shipped codes in order"
    )
    for descriptor in payload["rules"]:
        assert set(descriptor) == _DESCRIPTOR_KEYS, (
            "expected exactly the documented descriptor keys"
        )
        assert isinstance(descriptor["fixable"], bool), "expected a JSON boolean"
        assert isinstance(descriptor["requires"], list), "expected an array"
        assert isinstance(descriptor["targets"], list), "expected an array"
        assert isinstance(descriptor["examples"], list), "expected an array"
        assert set(descriptor["targets"][0]) == {"syntax", "kinds", "scope_has"}, (
            "expected the documented target shape"
        )


def test_json_list_and_detail_describe_the_same_rule() -> None:
    """The descriptor is identical in both envelopes, as the contract states."""
    _status, list_output, _error = list_result(output_format="json")
    listed = {
        descriptor["code"]: descriptor
        for descriptor in json.loads(list_output)["rules"]
    }

    for code in _CODES:
        _status, detail_output, _error = detail_result(code, "json")
        assert json.loads(detail_output)["rule"] == listed[code], (
            "expected the detail descriptor to equal the listed descriptor"
        )


def test_json_detail_documents_term001_defaults_and_variants() -> None:
    """The opt-in rule's declared option types match the parser contract."""
    _status, output, _error = detail_result("TERM001", "json")
    payload = json.loads(output)
    descriptor = payload["rule"]

    assert payload["schema_version"] == 1, "expected schema version 1"
    assert descriptor["enabled_by_default"] is False, "expected opt-in"
    assert descriptor["fix_mode"] == "none", "expected no fix"
    options = {
        option["name"]: option for option in descriptor["configuration"]["options"]
    }
    assert options["terms"]["type"] == "array[string]", "expected an array option"
    assert options["terms"]["default"] == [], "expected the empty term default"
    assert options["case_sensitive"]["type"] == "boolean", "expected a boolean option"
    assert options["case_sensitive"]["default"] is False, (
        "expected case-insensitive matching by default"
    )
    assert [variant["value"] for variant in options["case_sensitive"]["variants"]] == [
        False,
        True,
    ], "expected false then true variants"


def test_json_output_is_deterministic() -> None:
    """Repeated rendering produces byte-identical JSON."""
    first = list_result(output_format="json")
    second = list_result(output_format="json")

    assert first == second, "expected deterministic JSON output"
    assert detail_result("TERM001", "json") == detail_result("TERM001", "json"), (
        "expected deterministic detail JSON"
    )


def test_text_output_is_deterministic() -> None:
    """Repeated rendering produces byte-identical text."""
    assert list_result() == list_result(), "expected deterministic list text"
    assert detail_result("MD001") == detail_result("MD001"), (
        "expected deterministic detail text"
    )


@pytest.mark.parametrize("output_format", ["yaml", "sarif", ""])
def test_renderers_reject_an_unsupported_format(output_format: str) -> None:
    """A caller that bypasses the parser still cannot request a format."""
    rule = catalogue.get_rule("MD001")

    with pytest.raises(ValueError, match="output format"):
        render_rule_list([rule], output_format)
    with pytest.raises(ValueError, match="output format"):
        render_rule_detail(rule, output_format)


def test_check_dispatch_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check` remains the default command with its original targets."""
    calls: list[tuple[str, ...]] = []

    def fake_run_check(options: cli.CheckOptions) -> int:
        """Record the check options this dispatch produced."""
        calls.append(options.targets)
        return 0

    monkeypatch.setattr(cli, "run_check", fake_run_check)

    assert cli.main([]) == 0, "expected no arguments to dispatch check"
    assert cli.main(["check", "docs/notes.md"]) == 0, (
        "expected an explicit check command to dispatch check"
    )
    assert calls == [(".",), ("docs/notes.md",)], (
        "expected check dispatch to keep its default and explicit targets"
    )
