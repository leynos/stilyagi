//! BDD coverage for Markdown suppression directives in extracted IR.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::{IrDocument, RangeRole, SuppressionKind};

#[derive(Default)]
struct MarkdownSuppressionState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn markdown_suppression_state() -> MarkdownSuppressionState {
    MarkdownSuppressionState::default()
}

const fn extracted_ir(state: &MarkdownSuppressionState) -> &IrDocument {
    let Some(document) = state.document.as_ref() else {
        panic!("expected extracted Markdown document");
    };
    let Some(ir) = document.ir() else {
        panic!("expected Markdown IR to be present");
    };
    ir
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
fn the_document_is_extracted(markdown_suppression_state: &mut MarkdownSuppressionState) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };

    markdown_suppression_state.document =
        Some(match extract_document(source, ExtractSyntax::Markdown) {
            Ok(document) => document,
            Err(error) => panic!("expected Markdown extraction to succeed: {error}"),
        });
}

#[then("the IR suppressions contain one inline entry naming PUN201")]
fn the_ir_suppressions_contain_one_inline_entry_naming_pun201(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let ir = extracted_ir(markdown_suppression_state);

    assert_eq!(ir.suppressions.len(), 1);
    let Some(suppression) = ir.suppressions.first() else {
        panic!("expected a suppression entry");
    };
    assert_eq!(suppression.kind, SuppressionKind::Inline);
    assert_eq!(suppression.codes, vec!["PUN201".to_owned()]);
}

#[then("the suppression span re-slices to the directive comment")]
fn the_suppression_span_re_slices_to_the_directive_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);

    assert_eq!(ir.suppressions.len(), 1);
    let Some(suppression) = ir.suppressions.first() else {
        panic!("expected a suppression entry");
    };
    assert_eq!(
        source.get(suppression.span.byte_start..suppression.span.byte_end),
        Some("<!-- stilyagi: ignore-next PUN201 -->")
    );
}

#[then("the IR suppressions are empty")]
fn the_ir_suppressions_are_empty(markdown_suppression_state: &MarkdownSuppressionState) {
    let ir = extracted_ir(markdown_suppression_state);

    assert!(ir.suppressions.is_empty());
}

#[then("the IR suppressions contain two range entries naming STY")]
fn the_ir_suppressions_contain_two_range_entries_naming_sty(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let ir = extracted_ir(markdown_suppression_state);

    assert!(ir.errors.is_empty());
    assert_eq!(ir.suppressions.len(), 2);
    for suppression in &ir.suppressions {
        assert_eq!(suppression.kind, SuppressionKind::Range);
        assert_eq!(suppression.codes, vec!["STY".to_owned()]);
    }
}

#[then("the IR errors contain a blanket-forbidden entry for the second comment")]
fn the_ir_errors_contain_a_blanket_forbidden_entry_for_the_second_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);
    let Some(error) = ir
        .errors
        .iter()
        .find(|error| error.code == "suppression-blanket-forbidden")
    else {
        panic!("expected a blanket suppression error");
    };
    let Some(span) = error.span else {
        panic!("expected suppression error span");
    };

    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some("<!-- stilyagi: disable -->")
    );
}

#[then("the blanket error span re-slices to the second coalesced comment")]
fn the_blanket_error_span_re_slices_to_the_second_coalesced_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);
    let Some(error) = ir
        .errors
        .iter()
        .find(|error| error.code == "suppression-blanket-forbidden")
    else {
        panic!("expected a blanket suppression error");
    };
    let Some(span) = error.span else {
        panic!("expected suppression error span");
    };

    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some("<!-- stilyagi: disable -->")
    );
}

#[then("the suppression spans re-slice to the coalesced comments")]
fn the_suppression_spans_re_slice_to_the_coalesced_comments(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);

    assert_eq!(ir.suppressions.len(), 2);
    let expected_comments = [
        "<!-- stilyagi: disable STY -->",
        "<!-- stilyagi: enable STY -->",
    ];

    for (suppression, expected_comment) in ir.suppressions.iter().zip(expected_comments) {
        assert_eq!(
            source.get(suppression.span.byte_start..suppression.span.byte_end),
            Some(expected_comment)
        );
    }
}

#[then("the IR suppressions contain one range entry naming STY")]
fn the_ir_suppressions_contain_one_range_entry_naming_sty(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let ir = extracted_ir(markdown_suppression_state);

    assert_eq!(ir.errors.len(), 1);
    assert_eq!(ir.suppressions.len(), 1);
    let Some(suppression) = ir.suppressions.first() else {
        panic!("expected a suppression entry");
    };
    assert_eq!(suppression.kind, SuppressionKind::Range);
    assert_eq!(suppression.codes, vec!["STY".to_owned()]);
}

#[then("the suppression span re-slices to the first coalesced comment")]
fn the_suppression_span_re_slices_to_the_first_coalesced_comment(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);
    let Some(suppression) = ir.suppressions.first() else {
        panic!("expected a suppression entry");
    };

    assert_eq!(
        source.get(suppression.span.byte_start..suppression.span.byte_end),
        Some("<!-- stilyagi: disable STY -->")
    );
}

#[then("the IR errors contain a blanket-forbidden entry")]
fn the_ir_errors_contain_a_blanket_forbidden_entry(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let Some(source) = markdown_suppression_state.source.as_deref() else {
        panic!("expected Markdown source to be configured");
    };
    let ir = extracted_ir(markdown_suppression_state);
    let Some(error) = ir
        .errors
        .iter()
        .find(|error| error.code == "suppression-blanket-forbidden")
    else {
        panic!("expected a blanket suppression error");
    };
    let Some(span) = error.span else {
        panic!("expected suppression error span");
    };

    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some("<!-- stilyagi: disable -->")
    );
}

#[then("the first IR suppression records the disable as a range open")]
fn the_first_ir_suppression_records_the_disable_as_a_range_open(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let ir = extracted_ir(markdown_suppression_state);
    let Some(suppression) = ir.suppressions.first() else {
        panic!("expected a suppression entry");
    };

    assert_eq!(ir.suppressions.len(), 2);
    assert_eq!(suppression.kind, SuppressionKind::Range);
    assert_eq!(suppression.codes, vec!["STY".to_owned()]);
    assert_eq!(suppression.range_role, Some(RangeRole::Open));
}

#[then("the second IR suppression records the enable as a range close")]
fn the_second_ir_suppression_records_the_enable_as_a_range_close(
    markdown_suppression_state: &MarkdownSuppressionState,
) {
    let ir = extracted_ir(markdown_suppression_state);
    let Some(suppression) = ir.suppressions.get(1) else {
        panic!("expected a second suppression entry");
    };

    assert_eq!(ir.suppressions.len(), 2);
    assert_eq!(suppression.kind, SuppressionKind::Range);
    assert_eq!(suppression.codes, vec!["STY".to_owned()]);
    assert_eq!(suppression.range_role, Some(RangeRole::Close));
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
