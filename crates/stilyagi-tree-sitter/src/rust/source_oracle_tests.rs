//! Property tests for Rust source-backed segment byte oracles.

use proptest::prelude::*;

use crate::test_support::{assert_segments_match_source, extract_rust};

#[test]
fn crlf_empty_line_and_mixed_whitespace_doc_comments_match_the_source_oracle() {
    let source = concat!(
        "/// First line\r\n",
        "///\r\n",
        "///\tThird line\r\n",
        "pub fn crlf_doc_comment() {}\r\n",
    );
    let document = extract_rust(source).expect("expected Rust extraction");
    let region = document
        .regions
        .first()
        .expect("expected a merged Rust doc-comment region");

    assert_eq!(document.regions.len(), 1);
    assert_eq!(region.text, " First line  \tThird line");
    assert!(region.segments_reconstruct_text());
    assert_segments_match_source!(&document, source);
}

proptest! {
    #[test]
    fn line_doc_comment_segments_match_the_source_oracle(
        content in "[A-Za-z0-9_ ]{1,12}",
    ) {
        let source = format!("/// {content}\npub fn line_doc_comment() {{}}\n");
        let document = extract_rust(&source).expect("expected Rust extraction");

        assert_segments_match_source!(&document, &source);
    }

    #[test]
    fn merged_line_doc_comment_segments_match_the_source_oracle(
        first in "[A-Za-z0-9_ ]{1,8}",
        second in "[A-Za-z0-9_ ]{1,8}",
    ) {
        let source = format!(
            "/// {first}\n/// {second}\npub fn merged_line_doc_comment() {{}}\n"
        );
        let document = extract_rust(&source).expect("expected Rust extraction");

        assert_segments_match_source!(&document, &source);
    }

    #[test]
    fn block_doc_comment_segments_match_the_source_oracle(
        content in "[A-Za-z0-9_ ]{1,16}",
    ) {
        let source = format!("/** {content} */\npub fn block_doc_comment() {{}}\n");
        let document = extract_rust(&source).expect("expected Rust extraction");

        assert_segments_match_source!(&document, &source);
    }
}
