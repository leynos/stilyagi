//! Then steps that assert the extracted Markdown suppression IR.

use rstest_bdd_macros::then;
use stilyagi_ir::{IrDocument, IrSuppression, RangeRole, SuppressionKind};

use super::{
    MarkdownSuppressionState, assert_blanket_error_re_slices_to_the_blanket_comment,
    configured_source, extracted_ir,
};
use crate::test_utils::{ensure, ensure_eq};

/// Return the suppression at `index`, or an error naming the missing entry.
fn suppression_at(ir: &IrDocument, index: usize) -> Result<&IrSuppression, &'static str> {
    ir.suppressions
        .get(index)
        .ok_or("expected a suppression entry at the requested index")
}

/// Assert the IR carries exactly `count` suppressions.
fn assert_suppression_count(
    ir: &IrDocument,
    count: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    ensure_eq(
        &ir.suppressions.len(),
        &count,
        "suppression count did not match the scenario",
    )
}

/// Assert `suppression` has `kind` and names only the `code` directive.
fn assert_suppression_names(
    suppression: &IrSuppression,
    kind: SuppressionKind,
    code: &'static str,
) -> Result<(), Box<dyn std::error::Error>> {
    ensure(
        suppression.kind == kind,
        "suppression kind did not match the scenario",
    )?;
    ensure_eq(
        &suppression.codes,
        &vec![code.to_owned()],
        "suppression codes did not match the scenario",
    )
}

/// Assert the suppression's span re-slices to `expected`.
fn assert_span_re_slices_to(
    source: &str,
    suppression: &IrSuppression,
    expected: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    ensure_eq(
        &source.get(suppression.span.byte_start..suppression.span.byte_end),
        &Some(expected),
        "suppression span did not re-slice to the expected comment",
    )
}

#[then("the IR suppressions contain one inline entry naming PUN201")]
fn the_ir_suppressions_contain_one_inline_entry_naming_pun201(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(markdown_suppression_state)?;
    assert_suppression_count(ir, 1)?;
    assert_suppression_names(suppression_at(ir, 0)?, SuppressionKind::Inline, "PUN201")
}

#[then("the suppression span re-slices to the directive comment")]
fn the_suppression_span_re_slices_to_the_directive_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(markdown_suppression_state)?;
    let ir = extracted_ir(markdown_suppression_state)?;
    assert_suppression_count(ir, 1)?;
    assert_span_re_slices_to(
        source,
        suppression_at(ir, 0)?,
        "<!-- stilyagi: ignore-next PUN201 -->",
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
    assert_suppression_count(ir, 2)?;
    for suppression in &ir.suppressions {
        assert_suppression_names(suppression, SuppressionKind::Range, "STY")?;
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
    let expected_comments = [
        "<!-- stilyagi: disable STY -->",
        "<!-- stilyagi: enable STY -->",
    ];

    assert_suppression_count(ir, 2)?;
    for (suppression, expected_comment) in ir.suppressions.iter().zip(expected_comments) {
        assert_span_re_slices_to(source, suppression, expected_comment)?;
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
    assert_suppression_count(ir, 1)?;
    assert_suppression_names(suppression_at(ir, 0)?, SuppressionKind::Range, "STY")
}

#[then("the suppression span re-slices to the first coalesced comment")]
fn the_suppression_span_re_slices_to_the_first_coalesced_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(markdown_suppression_state)?;
    let ir = extracted_ir(markdown_suppression_state)?;
    assert_span_re_slices_to(
        source,
        suppression_at(ir, 0)?,
        "<!-- stilyagi: disable STY -->",
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
    assert_suppression_count(ir, 2)?;
    let suppression = suppression_at(ir, 0)?;
    assert_suppression_names(suppression, SuppressionKind::Range, "STY")?;
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
    assert_suppression_count(ir, 2)?;
    let suppression = suppression_at(ir, 1)?;
    assert_suppression_names(suppression, SuppressionKind::Range, "STY")?;
    ensure_eq(
        &suppression.range_role,
        &Some(RangeRole::Close),
        "expected the second suppression to close the range",
    )
}
