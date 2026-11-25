"""Contract tests for the description records' own consistency checks.

The catalogue promises that a shipped descriptor cannot contradict itself:
capabilities are sorted and known, the fix mode is in the published
vocabulary, typed option defaults match their declared type, boolean variants
are false then true, and capability declarations agree with `requires_nlp`.
These tests construct deliberately broken records and assert that each
constructor rejects them, so the metadata contract is enforced rather than
merely documented.
"""

import dataclasses as dc
import typing as typ

import pytest
from stilyagi.rules.base import RegionTarget, RuleMetadata
from stilyagi.rules.description import (
    OptionVariant,
    RuleConfiguration,
    RuleDescription,
    RuleExample,
    RuleOption,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _description() -> RuleDescription:
    """Return one minimal valid description for mutation in a test."""
    return RuleDescription(
        summary="summary",
        explanation="explanation",
        requires=("STRUCTURE",),
        fix_mode="manual",
        enabled_by_default=True,
        configuration=RuleConfiguration("selected"),
        fixes="manual guidance",
    )


def _metadata() -> RuleMetadata:
    """Return one minimal valid rule descriptor for mutation in a test."""
    return RuleMetadata(
        code="MD001",
        name="heading-depth",
        target=RegionTarget(kinds=("heading",)),
        default_severity="error",
        description=_description(),
    )


def _boolean_option() -> RuleOption:
    """Return one valid boolean option for mutation in a test."""
    return RuleOption(
        name="case_sensitive",
        type="boolean",
        default=False,
        description="compare exact case",
        variants=(
            OptionVariant(value=False, description="fold case"),
            OptionVariant(value=True, description="exact case"),
        ),
    )


def _array_option() -> RuleOption:
    """Return one valid array option for mutation in a test."""
    return RuleOption(
        name="terms",
        type="array[string]",
        default=(),
        description="terms to report",
    )


def test_valid_records_construct_without_error() -> None:
    """The valid counterparts of every rejection case construct successfully.

    The negative cases above only prove that a validator fires. This positive
    control proves the checks accept the shapes the catalogue actually ships,
    so a validator that rejected everything would not pass unnoticed.
    """
    description = _description()
    metadata = _metadata()
    boolean = _boolean_option()
    array = _array_option()
    filled_array = RuleOption(
        name="terms",
        type="array[string]",
        default=("one", "two"),
        description="terms to report",
    )

    assert description.fixable is False, "expected manual mode not to be fixable"
    assert metadata.code == "MD001", "expected the descriptor to retain its code"
    assert boolean.variants[0].value is False, "expected false then true"
    assert array.default == (), "expected the empty array default"
    assert filled_array.default == ("one", "two"), (
        "expected a non-empty string tuple default to be accepted"
    )
    assert RuleConfiguration("selected", options=(boolean, array)).options == (
        boolean,
        array,
    ), "expected distinct option names to be accepted"


@pytest.mark.parametrize(
    ("factory", "error", "match"),
    [
        pytest.param(
            lambda: OptionVariant(value=typ.cast("bool", "yes"), description="x"),
            TypeError,
            "variant value must be a boolean",
            id="variant-not-boolean",
        ),
        pytest.param(
            lambda: RuleOption(
                name="",
                type="boolean",
                default=False,
                description="x",
                variants=(
                    OptionVariant(value=False, description="x"),
                    OptionVariant(value=True, description="x"),
                ),
            ),
            ValueError,
            "name must be non-empty",
            id="empty-option-name",
        ),
        pytest.param(
            lambda: dc.replace(_boolean_option(), default=()),
            TypeError,
            "needs a boolean default",
            id="boolean-default-not-bool",
        ),
        pytest.param(
            lambda: dc.replace(
                _boolean_option(),
                variants=(
                    OptionVariant(value=True, description="x"),
                    OptionVariant(value=False, description="x"),
                ),
            ),
            ValueError,
            "false then true variants",
            id="boolean-variant-order",
        ),
        pytest.param(
            lambda: dc.replace(_array_option(), default=False),
            TypeError,
            "needs a tuple default",
            id="array-default-not-tuple",
        ),
        pytest.param(
            lambda: dc.replace(
                _array_option(),
                default=(typ.cast("str", 1),),
            ),
            TypeError,
            "only string elements",
            id="array-element-not-string",
        ),
        pytest.param(
            lambda: dc.replace(
                _array_option(),
                variants=(OptionVariant(value=False, description="x"),),
            ),
            ValueError,
            "cannot declare variants",
            id="array-with-variants",
        ),
    ],
)
def test_option_records_reject_contradictions(
    factory: cabc.Callable[[], object],
    error: type[Exception],
    match: str,
) -> None:
    """A typed option whose shape contradicts its declaration is rejected."""
    with pytest.raises(error, match=match):
        factory()


def test_configuration_rejects_duplicate_option_names() -> None:
    """Two options with one name would make the rendered documentation lie."""
    with pytest.raises(ValueError, match="unique"):
        RuleConfiguration("selected", options=(_array_option(), _array_option()))


@pytest.mark.parametrize(
    ("changes", "error", "match"),
    [
        pytest.param(
            {"requires": ("TOKENS", "STRUCTURE")},
            ValueError,
            "sorted and unique",
            id="unsorted-requires",
        ),
        pytest.param(
            {"requires": ("STRUCTURE", "STRUCTURE")},
            ValueError,
            "sorted and unique",
            id="duplicate-requires",
        ),
        pytest.param(
            {"requires": ("UNKNOWN",)},
            ValueError,
            "unsupported capability",
            id="unknown-capability",
        ),
        pytest.param(
            {"fix_mode": "sometimes"},
            ValueError,
            "unsupported fix mode",
            id="unknown-fix-mode",
        ),
        pytest.param(
            {"preview": "no"},
            TypeError,
            "preview",
            id="preview-not-boolean",
        ),
    ],
)
def test_description_rejects_contradictions(
    changes: dict[str, object],
    error: type[Exception],
    match: str,
) -> None:
    """A description whose policy fields contradict the vocabulary is rejected."""
    with pytest.raises(error, match=match):
        dc.replace(_description(), **changes)


def _example() -> RuleExample:
    """Return one valid executable example for mutation in a test."""
    return RuleExample(
        title="A finding",
        source="# Start\n### Detail\n",
        configuration="",
        expected_codes=("MD001", "STY001"),
    )


def test_example_preserves_authored_order_and_codes() -> None:
    """An example is data only; its fields and code order are retained."""
    example = _example()

    assert example.expected_codes == ("MD001", "STY001"), (
        "expected the observed code order to be preserved"
    )
    assert not example.configuration, "expected an empty configuration to stay empty"
    assert not hasattr(example, "exit_code"), (
        "expected the domain record to carry no check-policy status"
    )


@pytest.mark.parametrize(
    ("changes", "error", "match"),
    [
        pytest.param({"code": ""}, ValueError, "code", id="empty-code"),
        pytest.param({"name": ""}, ValueError, "name", id="empty-name"),
        pytest.param({"pack": ""}, ValueError, "pack", id="empty-pack"),
        pytest.param(
            {"default_severity": "fatal"},
            ValueError,
            "default severity",
            id="unknown-severity",
        ),
        pytest.param(
            {"requires_nlp": True},
            ValueError,
            "requires_nlp",
            id="nlp-capability-mismatch",
        ),
    ],
)
def test_metadata_rejects_contradictions(
    changes: dict[str, object],
    error: type[Exception],
    match: str,
) -> None:
    """A descriptor whose identity or capability metadata contradicts is rejected."""
    with pytest.raises(error, match=match):
        dc.replace(_metadata(), **changes)
