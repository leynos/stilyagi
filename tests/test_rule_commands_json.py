"""JSON contract coverage for the builtin rule discovery commands.

The JSON envelope is a published, schema-versioned contract, so its shape is
asserted apart from the text rendering. These tests check the envelope keys,
the complete descriptor key set, that list and detail agree, that the opt-in
rule's typed options survive serialization, and that repeated rendering is
byte-identical.
"""

import json

from tests.support.rule_command_support import detail_result, list_result

_CODES = ("DOC001", "DOC002", "DOC003", "MD001", "STY001", "TERM001")
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
        assert set(descriptor["targets"][0]) == {
            "syntax",
            "kinds",
            "scope_has",
            "owner_kinds",
        }, "expected the documented target shape"


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
