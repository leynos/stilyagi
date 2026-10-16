"""Tests for the public fix value model."""

import typing as typ

from stilyagi.engine.ir_view import SourceSpan
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context


def test_fix_coerces_rule_authored_values_into_the_strict_model() -> None:
    """Accept the RFC's string applicability and list edit examples."""
    edit = TextEdit(3, 3, ",")
    # The loose values are this test's whole subject, so they cannot be
    # tightened without deleting what it proves. The casts are no-ops at
    # runtime: the string and the list still arrive at `Fix.__post_init__`,
    # which is what has to coerce them. They only tell the type checker what
    # the RFC permits an untyped rule author to write.
    coarse_applicability = typ.cast("Applicability", "safe")
    # The list is cast to `Any` rather than to `list[TextEdit]`, because the
    # looser annotation would be a lie the checker can see through: a list of
    # `TextEdit` is already what it would infer, so the cast would assert
    # nothing while still failing the `tuple` parameter it is passed to. What
    # the RFC actually admits here is a value of unknown static type.
    coarse_edits = typ.cast("typ.Any", [edit])
    fix = Fix(
        title="Insert comma",
        applicability=coarse_applicability,
        edits=coarse_edits,
    )

    assert_with_context(
        fix.applicability is Applicability.SAFE,
        "expected the string applicability to coerce to Applicability.SAFE",
    )
    assert_with_context(
        fix.edits == (edit,),
        "expected the rule-authored edit list to coerce to a tuple",
    )
    assert hash(fix), "expected a frozen Fix to remain hashable"


def test_text_edit_replacement_and_order_use_byte_spans() -> None:
    """Construct and order byte-oriented edit requests deterministically."""
    span = SourceSpan(2, 4)

    assert_with_context(
        TextEdit.replace(span, "x") == TextEdit(2, 4, "x"),
        "expected replace to target the complete span",
    )
    assert_with_context(
        TextEdit.replace(span, "") == TextEdit(2, 4, ""),
        "expected an empty replacement to delete the complete span",
    )
    assert_with_context(
        sorted((TextEdit(1, 2, "z"), TextEdit(1, 2, "a")))
        == [TextEdit(1, 2, "a"), TextEdit(1, 2, "z")],
        "expected replacement text to break equal-span ordering ties",
    )
