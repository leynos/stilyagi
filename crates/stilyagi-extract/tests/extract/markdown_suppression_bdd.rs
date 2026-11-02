//! BDD coverage for Markdown suppression directives in extracted IR.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::{IrDocument, RangeRole, SuppressionKind};

use crate::test_utils::{ensure, ensure_eq};

#[derive(Default)]
struct MarkdownSuppressionState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn markdown_suppression_state() -> MarkdownSuppressionState {
    MarkdownSuppressionState::default()
}

const fn find_extracted_ir(state: &MarkdownSuppressionState) -> Option<&IrDocument> {
    let Some(document) = state.document.as_ref() else {
        return None;
    };
    document.ir()
}

/// Return the extracted Markdown IR or report the missing extraction step.
fn extracted_ir(state: &MarkdownSuppressionState) -> Result<&IrDocument, &'static str> {
    find_extracted_ir(state)
        .ok_or("expected an extracted Markdown IR payload; did the extraction step run?")
}

/// Return the configured Markdown source or report the missing setup step.
fn configured_source(state: &MarkdownSuppressionState) -> Result<&str, &'static str> {
    state
        .source
        .as_deref()
        .ok_or("expected Markdown source to be configured")
}

/// Returns the text the blanket-forbidden error span re-slices to, if any.
fn blanket_error_text<'a>(source: &'a str, ir: &IrDocument) -> Option<&'a str> {
    let error = ir
        .errors
        .iter()
        .find(|error| error.code == "suppression-blanket-forbidden")?;
    let span = error.span?;
    source.get(span.byte_start..span.byte_end)
}

#[track_caller]
fn assert_blanket_error_re_slices_to_the_blanket_comment(
    state: &MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = configured_source(state)?;
    let ir = extracted_ir(state)?;

    ensure_eq(
        &blanket_error_text(source, ir),
        &Some("<!-- stilyagi: disable -->"),
        "blanket error span should re-slice to the blanket comment",
    )
}

/// Missing BDD extraction state is reported without panicking.
#[test]
fn missing_extraction_state_returns_an_error() {
    let state = MarkdownSuppressionState::default();
    assert_eq!(
        extracted_ir(&state).expect_err("missing extraction should return an error"),
        "expected an extracted Markdown IR payload; did the extraction step run?"
    );
    assert_eq!(
        configured_source(&state).expect_err("missing source should return an error"),
        "expected Markdown source to be configured"
    );
}

#[given("a Markdown document with a \"stilyagi: ignore-next PUN201\" comment")]
fn a_markdown_document_with_an_ignore_next_comment(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some(
        concat!(
            "# Suppression Fixture\n\n",
            "<!-- stilyagi: ignore-next PUN201 -->\n",
            "Apples, bananas and pears.\n",
        )
        .to_owned(),
    );
}

#[given("a paragraph contains an inline \"stilyagi: ignore-next PUN201\" comment")]
fn a_paragraph_contains_an_inline_ignore_next_comment(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some(
        concat!(
            "# Suppression Fixture\n\n",
            "Apples <!-- stilyagi: ignore-next PUN201 --> and pears.\n",
        )
        .to_owned(),
    );
}

#[given("a Markdown document with a \"stilyagi: disable\" comment naming no code")]
fn a_markdown_document_with_a_blanket_disable_comment(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some("<!-- stilyagi: disable -->\n".to_owned());
}

#[given("a Markdown document with a \"stilyagi: disable STY\"/\"enable STY\" pair")]
fn a_markdown_document_with_a_disable_and_enable_pair(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some(
        concat!(
            "# Suppression Fixture\n\n",
            "<!-- stilyagi: disable STY -->\n",
            "Suppressed content stays hidden here.\n",
            "<!-- stilyagi: enable STY -->\n",
        )
        .to_owned(),
    );
}

#[given("a Markdown document with two same-line suppression comments")]
fn a_markdown_document_with_two_same_line_suppression_comments(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some(
        concat!(
            "<!-- stilyagi: disable STY --> ",
            "<!-- stilyagi: enable STY -->\n",
        )
        .to_owned(),
    );
}

#[given("a Markdown document with a same-line suppression and a blanket comment")]
fn a_markdown_document_with_a_same_line_suppression_and_a_blanket_comment(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) {
    markdown_suppression_state.source = Some(
        concat!(
            "<!-- stilyagi: disable STY --> ",
            "<!-- stilyagi: disable -->\n",
        )
        .to_owned(),
    );
}

#[when("the document is extracted")]
fn the_document_is_extracted(
    markdown_suppression_state: &mut MarkdownSuppressionState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = markdown_suppression_state
        .source
        .as_deref()
        .ok_or("expected Markdown source to be configured")?;

    markdown_suppression_state.document = Some(extract_document(source, ExtractSyntax::Markdown)?);
    Ok(())
}

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
#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "A canonical ignore-next directive becomes a suppression"
)]
fn a_canonical_ignore_next_directive_becomes_a_suppression(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}

#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "An inline directive within a paragraph becomes a suppression"
)]
fn an_inline_directive_within_a_paragraph_becomes_a_suppression(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}

#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "A range disable and enable pair record open and close polarity"
)]
fn a_range_disable_and_enable_pair_record_open_and_close_polarity(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}

#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "A blanket directive is refused"
)]
fn a_blanket_directive_is_refused(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}

#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "A same-line coalesced directive node becomes two suppressions"
)]
fn a_same_line_coalesced_directive_node_becomes_two_suppressions(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}

#[scenario(
    path = "tests/features/markdown_suppression.feature",
    name = "A mixed same-line suppression and blanket comment"
)]
fn a_same_line_suppression_and_a_blanket_comment_produce_one_suppression_and_one_error(
    #[from(markdown_suppression_state)] _markdown_suppression_state: MarkdownSuppressionState,
) {
}
