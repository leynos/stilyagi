//! Addendum tests for Rust doc-comment attachment and recovery behaviour.

use rstest::rstest;
use stilyagi_ir::SourceIdentity;

use super::rust_doc_comment_ir_document;

fn extract_rust(source: &str) -> stilyagi_ir::IrDocument {
    match rust_doc_comment_ir_document(source, SourceIdentity::anonymous()) {
        Ok(document) => document,
        Err(error) => panic!("expected Rust extraction: {error:?}"),
    }
}

#[rstest]
#[case(
    "/// Outer doc comment.\n// Ordinary comments should not break attachment.\npub struct CommentShielded;\n",
    Some(("struct", Some("CommentShielded"), Some("CommentShielded"))),
    " Outer doc comment."
)]
#[case(
    "pub mod container {\n    // Ordinary comments should not break attachment.\n    //! Inner doc comment after an ordinary comment.\n}\n",
    Some(("module", Some("container"), Some("container"))),
    " Inner doc comment after an ordinary comment."
)]
fn doc_comments_survive_intervening_non_doc_comments(
    #[case] source: &str,
    #[case] expected_owner: Option<(&str, Option<&str>, Option<&str>)>,
    #[case] expected_text: &str,
) {
    let document = extract_rust(source);
    let Some(region) = document.regions.first() else {
        panic!("expected an attached Rust doc-comment region");
    };

    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        region.owner.as_ref().map(|owner| {
            (
                owner.kind.as_str(),
                owner.name.as_deref(),
                owner.qualname.as_deref(),
            )
        }),
        expected_owner
    );
    assert_eq!(region.text, expected_text);
}

#[rstest]
fn doc_comments_absorbed_into_error_subtrees_emit_diagnostics() {
    let source = r#"//! Crate docs before malformed Rust source.

pub fn broken_function() {
    /// This doc comment is swallowed by the error subtree.
    let value = "unterminated block";
"#;
    let document = extract_rust(source);

    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "rust-doc-comment-error-subtree")
    );
    assert!(
        !document
            .regions
            .iter()
            .any(|region| region.text == " This doc comment is swallowed by the error subtree.")
    );
    assert!(
        document
            .regions
            .iter()
            .any(|region| region.text == " Crate docs before malformed Rust source.")
    );
}
