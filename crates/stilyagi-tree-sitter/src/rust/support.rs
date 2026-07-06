//! Parser and IR envelope support for Rust extraction.

use std::collections::{BTreeMap, BTreeSet};

use stilyagi_ir::{IrDocument, IrRegion, ProducerMetadata, suppression::validate_suppressions};
use tree_sitter::Parser;

use super::RustExtractError;

const RUST_GRAMMAR_VERSION: &str = "0.24.2";

/// Parse UTF-8 Rust source with the vendored tree-sitter grammar.
///
/// Returns the concrete syntax tree for `source`. Grammar installation
/// failures map to `GrammarLoad`; a parser refusal to produce a tree maps to
/// `NoParseTree`.
pub(super) fn parse_rust(source: &str) -> Result<tree_sitter::Tree, RustExtractError> {
    let mut parser = Parser::new();
    let language = tree_sitter_rust::LANGUAGE.into();
    parser
        .set_language(&language)
        .map_err(|_| RustExtractError::GrammarLoad)?;
    parser
        .parse(source, None)
        .ok_or(RustExtractError::NoParseTree)
}

/// Build producer metadata for Rust doc-comment IR.
pub(super) fn rust_producer() -> ProducerMetadata {
    let mut options = BTreeMap::new();
    options.insert(
        "doc_comment_content".to_owned(),
        serde_json::json!("verbatim"),
    );
    options.insert("node_store".to_owned(), serde_json::json!("bounded"));
    options.insert("owner_qualname".to_owned(), serde_json::json!("rust"));
    ProducerMetadata {
        kind: "tree-sitter".to_owned(),
        name: "tree-sitter-rust".to_owned(),
        version: RUST_GRAMMAR_VERSION.to_owned(),
        options,
    }
}

/// Validate Rust IR consistency in debug builds.
pub(super) fn validate_ir_consistency(document: &IrDocument, source: &str) {
    debug_assert!(document_metadata_matches_source(document, source));
    debug_assert!(regions_reconstruct_text(document));
    let node_ids = document
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<BTreeSet<_>>();
    debug_assert!(suppressions_remain_valid(
        &document.suppressions,
        source,
        &node_ids
    ));
    debug_assert!(segments_match_source(document, source));
}

fn document_metadata_matches_source(document: &IrDocument, source: &str) -> bool {
    document.document.content_hash == stilyagi_ir::content_hash_for(source)
        && document.line_index == stilyagi_ir::line_index_for(source)
}

fn regions_reconstruct_text(document: &IrDocument) -> bool {
    document
        .regions
        .iter()
        .all(IrRegion::segments_reconstruct_text)
}

fn suppressions_remain_valid(
    suppressions: &[stilyagi_ir::IrSuppression],
    source: &str,
    node_ids: &BTreeSet<&str>,
) -> bool {
    validate_suppressions(suppressions, source, node_ids).is_ok()
}

fn segments_match_source(document: &IrDocument, source: &str) -> bool {
    document.regions.iter().all(|region| {
        region.segments.iter().all(|segment| {
            segment.source.is_none_or(|span| {
                source.get(span.byte_start..span.byte_end) == Some(segment.text.as_str())
            })
        })
    })
}

#[cfg(test)]
mod tests {
    //! Regression guard keeping the grammar version metadata pinned in step
    //! with the `tree-sitter-rust` dependency.

    use super::RUST_GRAMMAR_VERSION;
    use super::{rust_producer, validate_ir_consistency};
    use stilyagi_ir::{DocumentMetadata, IrDocument, IrSuppression, SourceSpan, SuppressionKind};

    #[test]
    fn rust_grammar_version_matches_the_pinned_dependency() {
        let manifest = stilyagi_test_fixtures::read_corpus_fixture("Cargo.toml")
            .expect("workspace manifest should be readable");
        let pinned = manifest
            .lines()
            .find(|line| line.trim_start().starts_with("tree-sitter-rust "))
            .and_then(|line| line.split('"').nth(1))
            .expect("tree-sitter-rust should be pinned in the workspace manifest");

        assert_eq!(
            pinned, RUST_GRAMMAR_VERSION,
            "RUST_GRAMMAR_VERSION must match the pinned tree-sitter-rust version"
        );
    }

    #[cfg(debug_assertions)]
    #[test]
    #[should_panic(expected = "assertion failed: suppressions_remain_valid")]
    fn validate_ir_consistency_checks_suppressions_in_debug_builds() {
        let source = "";
        let mut document = IrDocument::empty(
            DocumentMetadata::new("rust", None, None, source),
            vec![rust_producer()],
            source,
        );
        document.suppressions.push(IrSuppression {
            id: "s0".to_owned(),
            kind: SuppressionKind::Inline,
            range_role: None,
            codes: vec!["RUST210".to_owned()],
            span: SourceSpan::new(0, 0).expect("expected valid empty span"),
            origin: "n1".to_owned(),
        });

        validate_ir_consistency(&document, source);
    }
}
