//! Tests for Rust suppression extraction.

use rstest::rstest;
use stilyagi_ir::{SourceIdentity, SuppressionKind};

use super::rust_doc_comment_ir_document;

fn extract_rust(source: &str) -> stilyagi_ir::IrDocument {
    match rust_doc_comment_ir_document(source, SourceIdentity::anonymous()) {
        Ok(document) => document,
        Err(error) => panic!("expected Rust extraction: {error:?}"),
    }
}

fn node_ids(document: &stilyagi_ir::IrDocument) -> Vec<&str> {
    document.nodes.iter().map(|node| node.id.as_str()).collect()
}

#[rstest]
#[case(
    concat!(
        "pub fn nested() {\n",
        "    // stilyagi: ignore-next RUST210\n",
        "    let value = 1;\n",
        "}\n",
    ),
    SuppressionKind::Inline,
    vec!["RUST210"],
)]
#[case(
    concat!(
        "pub fn file_scope() {\n",
        "    // stilyagi: ignore-file\n",
        "}\n",
    ),
    SuppressionKind::File,
    Vec::<&str>::new(),
)]
#[case(
    concat!(
        "pub fn range_scope() {\n",
        "    // stilyagi: enable RUST211\n",
        "}\n",
    ),
    SuppressionKind::Range,
    vec!["RUST211"],
)]
fn directive_comments_emit_expected_suppressions(
    #[case] source: &str,
    #[case] expected_kind: SuppressionKind,
    #[case] expected_codes: Vec<&str>,
) {
    let document = extract_rust(source);
    let suppression = document
        .suppressions
        .first()
        .expect("expected one assembled Rust suppression");

    assert_eq!(document.suppressions.len(), 1);
    assert_eq!(suppression.kind, expected_kind);
    assert_eq!(suppression.codes, expected_codes);
    assert_eq!(
        document
            .nodes
            .iter()
            .find(|node| node.id == suppression.origin)
            .expect("suppression origin should resolve to a source-backed node")
            .kind,
        "comment"
    );
    assert!(
        document
            .errors
            .iter()
            .all(|error| error.code != "suppression-blanket-forbidden")
    );
}

#[rstest]
fn blanket_directives_emit_errors_without_suppressions() {
    let document = extract_rust(concat!(
        "pub fn blanket() {\n",
        "    // stilyagi: disable\n",
        "}\n",
    ));

    assert!(document.suppressions.is_empty());
    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "suppression-blanket-forbidden")
    );
    assert_eq!(
        document
            .nodes
            .iter()
            .filter(|node| node.kind == "comment")
            .count(),
        1
    );
}

#[rstest]
fn non_marker_comments_do_not_allocate_nodes_or_suppressions() {
    let with_comment = extract_rust(concat!(
        "/// Documented function.\n",
        "pub fn documented() {}\n",
        "// stilyagi-disable-next-line RUST210\n",
    ));
    let without_comment = extract_rust(concat!(
        "/// Documented function.\n",
        "pub fn documented() {}\n",
    ));

    assert!(with_comment.suppressions.is_empty());
    assert_eq!(node_ids(&with_comment), node_ids(&without_comment));
}

#[rstest]
fn directives_inside_nested_and_recovered_subtrees_are_collected() {
    let document = extract_rust(concat!(
        "pub fn nested() {\n",
        "    // stilyagi: ignore-next RUST210\n",
        "    let value = 1;\n",
        "}\n",
        "\n",
        "pub fn broken() {\n",
        "    let value = \"unterminated;\n",
        "    // stilyagi: ignore-file\n",
    ));

    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "rust-parse-recovery")
    );
    assert_eq!(document.suppressions.len(), 2);
    assert_eq!(
        document
            .suppressions
            .first()
            .expect("expected first Rust suppression")
            .kind,
        SuppressionKind::Inline
    );
    assert_eq!(
        document
            .suppressions
            .get(1)
            .expect("expected second Rust suppression")
            .kind,
        SuppressionKind::File
    );
    assert_eq!(
        document
            .nodes
            .iter()
            .filter(|node| node.kind == "comment")
            .count(),
        2
    );
}
