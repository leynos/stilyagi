//! Then steps that assert the extracted Markdown suppression IR.

use rstest_bdd_macros::then;
use stilyagi_ir::{RangeRole, SuppressionKind};

use super::{
    MarkdownSuppressionState, assert_blanket_error_re_slices_to_the_blanket_comment,
    configured_source, extracted_ir,
};
use crate::test_utils::{ensure, ensure_eq};

#[then("the IR suppressions contain one inline entry naming PUN201")]
fn the_ir_suppressions_contain_one_inline_entry_naming_pun201(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure_eq(
        &ir.suppressions.len(),
        &1,
        "expected exactly one suppression entry",
    )?;
    let suppression = ir
        .suppressions
        .first()
        .ok_or("expected a suppression entry")?;
    ensure(
        suppression.kind == SuppressionKind::Inline,
        "expected the suppression to be inline",
    )?;
    ensure_eq(
        &suppression.codes,
        &vec!["PUN201".to_owned()],
        "expected the suppression to name PUN201",
    )
}

#[then("the suppression span re-slices to the directive comment")]
fn the_suppression_span_re_slices_to_the_directive_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(markdown_suppression_state)?;
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure_eq(
        &ir.suppressions.len(),
        &1,
        "expected exactly one suppression entry",
    )?;
    let suppression = ir
        .suppressions
        .first()
        .ok_or("expected a suppression entry")?;
    ensure_eq(
        &source.get(suppression.span.byte_start..suppression.span.byte_end),
        &Some("<!-- stilyagi: ignore-next PUN201 -->"),
        "suppression span should re-slice to the directive comment",
    )
}

#[then("the IR suppressions are empty")]
fn the_ir_suppressions_are_empty(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure(
        ir.suppressions.is_empty(),
        "expected no suppression entries",
    )
}

#[then("the IR suppressions contain two range entries naming STY")]
fn the_ir_suppressions_contain_two_range_entries_naming_sty(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure(ir.errors.is_empty(), "expected no extraction errors")?;
    ensure_eq(
        &ir.suppressions.len(),
        &2,
        "expected exactly two suppression entries",
    )?;
    for suppression in &ir.suppressions {
        ensure(
            suppression.kind == SuppressionKind::Range,
            "expected each suppression to be a range",
        )?;
        ensure_eq(
            &suppression.codes,
            &vec!["STY".to_owned()],
            "expected each suppression to name STY",
        )?;
    }
    Ok(())
}

#[then("the IR errors contain a blanket-forbidden entry for the second comment")]
fn the_ir_errors_contain_a_blanket_forbidden_entry_for_the_second_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    assert_blanket_error_re_slices_to_the_blanket_comment(markdown_suppression_state)?;
    Ok(())
}

#[then("the blanket error span re-slices to the second coalesced comment")]
fn the_blanket_error_span_re_slices_to_the_second_coalesced_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    assert_blanket_error_re_slices_to_the_blanket_comment(markdown_suppression_state)?;
    Ok(())
}

#[then("the suppression spans re-slice to the coalesced comments")]
fn the_suppression_spans_re_slice_to_the_coalesced_comments(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(markdown_suppression_state)?;
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure_eq(
        &ir.suppressions.len(),
        &2,
        "expected exactly two suppression entries",
    )?;
    let expected_comments = [
        "<!-- stilyagi: disable STY -->",
        "<!-- stilyagi: enable STY -->",
    ];

    for (suppression, expected_comment) in ir.suppressions.iter().zip(expected_comments) {
        ensure_eq(
            &source.get(suppression.span.byte_start..suppression.span.byte_end),
            &Some(expected_comment),
            "suppression span should re-slice to the coalesced comment",
        )?;
    }
    Ok(())
}

#[then("the IR suppressions contain one range entry naming STY")]
fn the_ir_suppressions_contain_one_range_entry_naming_sty(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;

    ensure_eq(
        &ir.errors.len(),
        &1,
        "expected exactly one extraction error",
    )?;
    ensure_eq(
        &ir.suppressions.len(),
        &1,
        "expected exactly one suppression entry",
    )?;
    let suppression = ir
        .suppressions
        .first()
        .ok_or("expected a suppression entry")?;
    ensure(
        suppression.kind == SuppressionKind::Range,
        "expected the suppression to be a range",
    )?;
    ensure_eq(
        &suppression.codes,
        &vec!["STY".to_owned()],
        "expected the suppression to name STY",
    )
}

#[then("the suppression span re-slices to the first coalesced comment")]
fn the_suppression_span_re_slices_to_the_first_coalesced_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(markdown_suppression_state)?;
    let ir = extracted_ir(markdown_suppression_state)?;
    let suppression = ir
        .suppressions
        .first()
        .ok_or("expected a suppression entry")?;

    ensure_eq(
        &source.get(suppression.span.byte_start..suppression.span.byte_end),
        &Some("<!-- stilyagi: disable STY -->"),
        "suppression span should re-slice to the first coalesced comment",
    )
}

#[then("the IR errors contain a blanket-forbidden entry")]
fn the_ir_errors_contain_a_blanket_forbidden_entry(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    assert_blanket_error_re_slices_to_the_blanket_comment(markdown_suppression_state)?;
    Ok(())
}

#[then("the first IR suppression records the disable as a range open")]
fn the_first_ir_suppression_records_the_disable_as_a_range_open(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;
    let suppression = ir
        .suppressions
        .first()
        .ok_or("expected a suppression entry")?;

    ensure_eq(
        &ir.suppressions.len(),
        &2,
        "expected exactly two suppression entries",
    )?;
    ensure(
        suppression.kind == SuppressionKind::Range,
        "expected the suppression to be a range",
    )?;
    ensure_eq(
        &suppression.codes,
        &vec!["STY".to_owned()],
        "expected the suppression to name STY",
    )?;
    ensure_eq(
        &suppression.range_role,
        &Some(RangeRole::Open),
        "expected the first suppression to open the range",
    )
}

#[then("the second IR suppression records the enable as a range close")]
fn the_second_ir_suppression_records_the_enable_as_a_range_close(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;
    let suppression = ir
        .suppressions
        .get(1)
        .ok_or("expected a second suppression entry")?;

    ensure_eq(
        &ir.suppressions.len(),
        &2,
        "expected exactly two suppression entries",
    )?;
    ensure(
        suppression.kind == SuppressionKind::Range,
        "expected the suppression to be a range",
    )?;
    ensure_eq(
        &suppression.codes,
        &vec!["STY".to_owned()],
        "expected the suppression to name STY",
    )?;
    ensure_eq(
        &suppression.range_role,
        &Some(RangeRole::Close),
        "expected the second suppression to close the range",
    )
}
