//! BDD coverage for Markdown suppression directives in extracted IR.
//!
//! The step definitions live in the `given` and `then` submodules so each
//! module stays under the workspace's module size limit; this module owns the
//! shared state, the extraction step and the scenarios.

use rstest::fixture;
use rstest_bdd_macros::{scenario, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::IrDocument;

use crate::test_utils::ensure_eq;

#[path = "markdown_suppression_bdd/given.rs"]
mod given;
#[path = "markdown_suppression_bdd/then.rs"]
mod then;

#[derive(Default)]
struct MarkdownSuppressionState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn markdown_suppression_state() -> MarkdownSuppressionState {
    // `rstest` re-emits this body inside another block; keeping it multi-line
    // stops `fn_single_line` from collapsing the body of that inner block, which
    // rustc reports as `unused_braces` in the expansion.
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
