//! Tests for Markdown suppression directives and wiring.

use std::path::Path;

use markdown::mdast::Node;
use proptest::prelude::*;
use proptest::string::string_regex;
use rstest::rstest;
use stilyagi_ir::{IrDocument, SourceSpan, SuppressionKind};

use super::source_identity;
use crate::{
    markdown_ir_document, parse_markdown_ast, suppression::DirectiveError,
    suppression::DirectiveOutcome, suppression::DirectiveVerb,
    suppression::parse_comment_directive, suppression::verb_kind, validate_ir_consistency,
};

#[rstest]
#[case(
    "stilyagi: ignore-next PUN201",
    DirectiveVerb::IgnoreNext,
    &["PUN201"],
)]
#[case("stilyagi: disable STY", DirectiveVerb::Disable, &["STY"])]
#[case("stilyagi: enable STY", DirectiveVerb::Enable, &["STY"])]
#[case(
    "stilyagi: ignore-file MD,DOC",
    DirectiveVerb::IgnoreFile,
    &["MD", "DOC"],
)]
fn parse_comment_directive_parses_canonical_verbs(
    #[case] inner: &str,
    #[case] expected_verb: DirectiveVerb,
    #[case] expected_codes: &[&str],
) {
    let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(inner) else {
        panic!("expected parsed directive for {inner:?}");
    };

    assert_eq!(parsed.verb, expected_verb);
    assert_eq!(
        parsed.codes,
        expected_codes
            .iter()
            .map(|code| (*code).to_owned())
            .collect::<Vec<_>>()
    );
    assert_eq!(verb_kind(parsed.verb), expected_kind(expected_verb));
}

#[rstest]
#[case("stilyagi: ignore-next")]
#[case("stilyagi: disable")]
#[case("stilyagi: enable")]
fn parse_comment_directive_rejects_blanket_inline_and_range_directives(#[case] inner: &str) {
    let DirectiveOutcome::Rejected(error) = parse_comment_directive(inner) else {
        panic!("expected blanket rejection for {inner:?}");
    };

    assert_eq!(error, DirectiveError::BlanketForbidden);
}

#[rstest]
#[case("stilyagi: ignore-file")]
#[case("stilyagi-disable-next-line terminology")]
#[case("<!-- comment -->")]
fn parse_comment_directive_accepts_file_blankets_or_ignores_non_directives(#[case] inner: &str) {
    match parse_comment_directive(inner) {
        DirectiveOutcome::Parsed(parsed) => {
            assert_eq!(parsed.verb, DirectiveVerb::IgnoreFile);
            assert!(parsed.codes.is_empty());
        }
        DirectiveOutcome::NotADirective => {}
        DirectiveOutcome::Rejected(error) => {
            panic!("unexpected directive outcome: {error:?}")
        }
    }
}

#[rstest]
fn markdown_parser_exposes_html_comment_spans() {
    let source = "<!-- stilyagi: ignore-next PUN201 -->\n";
    let tree = parse_markdown_ast(source).expect("expected Markdown AST");
    let html = find_html_node(&tree).expect("expected html comment node");
    let position = html.position().expect("expected html node position");

    assert_eq!(
        source.get(position.start.offset..position.end.offset),
        Some("<!-- stilyagi: ignore-next PUN201 -->")
    );
}

#[rstest]
fn markdown_ir_document_collects_canonical_suppressions() {
    let source = concat!(
        "# Suppression Fixture\n\n",
        "<!-- stilyagi: ignore-next PUN201 -->\n",
        "Apples, bananas and pears.\n\n",
        "<!-- stilyagi: disable STY -->\n",
        "A questionable section.\n",
        "<!-- stilyagi: enable STY -->\n\n",
        "<!-- stilyagi: ignore-file MD,DOC -->\n",
    );
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let html_node_ids = html_node_ids(&document);
    let expectations = [
        (
            SuppressionKind::Inline,
            vec!["PUN201"],
            "<!-- stilyagi: ignore-next PUN201 -->",
        ),
        (
            SuppressionKind::Range,
            vec!["STY"],
            "<!-- stilyagi: disable STY -->",
        ),
        (
            SuppressionKind::Range,
            vec!["STY"],
            "<!-- stilyagi: enable STY -->",
        ),
        (
            SuppressionKind::File,
            vec!["MD", "DOC"],
            "<!-- stilyagi: ignore-file MD,DOC -->",
        ),
    ];

    assert_eq!(document.errors, Vec::new());
    assert_eq!(document.suppressions.len(), expectations.len());
    for (((suppression, expected), node_id), index) in document
        .suppressions
        .iter()
        .zip(expectations)
        .zip(html_node_ids)
        .zip(0..)
    {
        assert_eq!(suppression.kind, expected.0, "suppression #{index}");
        assert_eq!(suppression.codes, expected.1, "suppression #{index}");
        assert_eq!(suppression.origin, node_id, "suppression #{index}");
        assert_eq!(
            source.get(suppression.span.byte_start..suppression.span.byte_end),
            Some(expected.2),
            "suppression #{index}"
        );
    }
}

#[rstest]
fn codeless_file_directives_produce_one_file_suppression() {
    let source = "<!-- stilyagi: ignore-file -->\nBody\n";
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let suppression = document
        .suppressions
        .first()
        .expect("expected a suppression");

    assert_eq!(document.suppressions.len(), 1);
    assert_eq!(suppression.kind, SuppressionKind::File);
    assert!(suppression.codes.is_empty());
    assert_eq!(
        source.get(suppression.span.byte_start..suppression.span.byte_end),
        Some("<!-- stilyagi: ignore-file -->")
    );
    assert!(document.errors.is_empty());
}

#[rstest]
#[case("<!-- stilyagi: ignore-next -->\n")]
#[case("<!-- stilyagi: disable -->\n")]
fn blanket_inline_and_range_directives_emit_errors_only(#[case] source: &str) {
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");

    assert!(document.suppressions.is_empty());
    assert_eq!(document.errors.len(), 1);
    let error = document
        .errors
        .first()
        .expect("expected a blanket suppression error");
    let span = error.span.expect("expected suppression error span");

    assert_eq!(error.code, "suppression-blanket-forbidden");
    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some(source.trim_end())
    );
}

#[rstest]
fn placeholder_non_canonical_marker_is_ignored() {
    let source = "<!-- stilyagi-disable-next-line terminology -->\n";
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");

    assert!(document.suppressions.is_empty());
    assert!(document.errors.is_empty());
}

#[rstest]
fn validate_ir_consistency_rejects_invalid_suppression_spans() {
    let source = "<!-- stilyagi: ignore-file -->\nBody\n";
    let mut document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    document
        .suppressions
        .first_mut()
        .expect("expected a suppression to mutate")
        .span = SourceSpan {
        byte_start: 0,
        byte_end: source.len() + 1,
    };

    let result = validate_ir_consistency(
        &document,
        source,
        &crate::MarkdownDiagnosticContext {
            phase: "validate",
            path: "docs/example.md",
            uri: "file:///repo/docs/example.md",
        },
    );

    let Err(error) = result else {
        panic!("expected invalid suppression span to fail validation");
    };
    assert_eq!(error.rule_id.as_ref(), "ir-suppression-source-mismatch");
}

proptest! {
    #[test]
    fn parse_comment_directive_preserves_trimmed_codes(
        verb in prop_oneof![
            Just("ignore-next"),
            Just("disable"),
            Just("enable"),
            Just("ignore-file"),
        ],
        codes_and_padding in directive_codes_and_padding(),
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let (codes, padding) = codes_and_padding;
        let mut body = format!("{leading_ws}stilyagi: {verb}");
        if let Some(first_code) = codes.first() {
            body.push(' ');
            body.push_str(first_code);
            for (code, pad) in codes.iter().skip(1).zip(padding.iter()) {
                body.push(',');
                body.push_str(pad);
                body.push_str(code);
            }
        }
        body.push_str(&trailing_ws);

        let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(&body) else {
            panic!("expected parsed directive for {body:?}");
        };

        prop_assert_eq!(parsed.codes, codes);
        prop_assert_eq!(verb_kind(parsed.verb), expected_kind_from_token(verb));
    }

    #[test]
    fn ignore_next_disable_and_enable_require_codes(
        verb in prop_oneof![Just("ignore-next"), Just("disable"), Just("enable")],
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let body = format!("{leading_ws}stilyagi: {verb}{trailing_ws}");
        let DirectiveOutcome::Rejected(error) = parse_comment_directive(&body) else {
            panic!("expected blanket rejection for {body:?}");
        };

        prop_assert_eq!(error, DirectiveError::BlanketForbidden);
    }

    #[test]
    fn ignore_file_allows_empty_codes(
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let body = format!("{leading_ws}stilyagi: ignore-file{trailing_ws}");
        let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(&body) else {
            panic!("expected parsed ignore-file directive for {body:?}");
        };

        prop_assert_eq!(parsed.verb, DirectiveVerb::IgnoreFile);
        prop_assert!(parsed.codes.is_empty());
    }
}

fn expected_kind(verb: DirectiveVerb) -> SuppressionKind {
    verb_kind(verb)
}

fn expected_kind_from_token(token: &str) -> SuppressionKind {
    match token {
        "ignore-next" => SuppressionKind::Inline,
        "disable" | "enable" => SuppressionKind::Range,
        "ignore-file" => SuppressionKind::File,
        other => panic!("unexpected verb token {other:?}"),
    }
}

fn directive_codes_and_padding() -> impl Strategy<Value = (Vec<String>, Vec<String>)> {
    prop::collection::vec(code_token_strategy(), 1..5).prop_flat_map(|codes| {
        let padding_len = codes.len().saturating_sub(1);
        (
            Just(codes),
            prop::collection::vec(space_padding_strategy(), padding_len),
        )
    })
}

fn code_token_strategy() -> impl Strategy<Value = String> {
    string_regex("[A-Z][A-Z0-9]{0,7}").expect("valid code regex")
}

fn whitespace_strategy() -> impl Strategy<Value = String> {
    string_regex("[ \t]{0,3}").expect("valid whitespace regex")
}

fn space_padding_strategy() -> impl Strategy<Value = String> {
    string_regex("[ \t]{0,2}").expect("valid space padding regex")
}

fn html_node_ids(document: &IrDocument) -> Vec<String> {
    document
        .nodes
        .iter()
        .filter(|node| node.kind == "html")
        .map(|node| node.id.clone())
        .collect()
}

fn find_html_node(node: &Node) -> Option<&Node> {
    if matches!(node, Node::Html(_)) {
        return Some(node);
    }
    node.children()
        .and_then(|children| children.iter().find_map(find_html_node))
}
