"""Tests for the public fix value model."""

from stilyagi.engine.ir_view import SourceSpan
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context


def test_fix_coerces_rule_authored_values_into_the_strict_model() -> None:
    """Accept the RFC's string applicability and list edit examples."""
    edit = TextEdit.insert_before(SourceSpan(3, 3), ",")
    fix = Fix(title="Insert comma", applicability="safe", edits=[edit])

    assert_with_context(
        fix.applicability is Applicability.SAFE,
        "expected the string applicability to coerce to Applicability.SAFE",
    )
    assert_with_context(
        fix.edits == (edit,),
        "expected the rule-authored edit list to coerce to a tuple",
    )
    assert hash(fix), "expected a frozen Fix to remain hashable"


def test_text_edit_helpers_and_order_use_byte_spans() -> None:
    """Construct and order byte-oriented edit requests deterministically."""
    span = SourceSpan(2, 4)

    assert_with_context(
        TextEdit.insert_before(span, "x") == TextEdit(2, 2, "x"),
        "expected insert_before to target the span start",
    )
    assert_with_context(
        TextEdit.insert_after(span, "x") == TextEdit(4, 4, "x"),
        "expected insert_after to target the span end",
    )
    assert_with_context(
        TextEdit.replace(span, "x") == TextEdit(2, 4, "x"),
        "expected replace to target the complete span",
    )
    assert_with_context(
        TextEdit.delete(span) == TextEdit(2, 4, ""),
        "expected delete to replace the complete span with nothing",
    )
    assert_with_context(
        sorted((TextEdit(1, 2, "z"), TextEdit(1, 2, "a")))
        == [TextEdit(1, 2, "a"), TextEdit(1, 2, "z")],
        "expected replacement text to break equal-span ordering ties",
    )
