//! Given steps that seed the Markdown suppression BDD state.

use rstest_bdd_macros::given;

use super::MarkdownSuppressionState;

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
