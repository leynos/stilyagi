//! Parser and IR envelope support for Python extraction.

use std::collections::BTreeMap;

use stilyagi_ir::{IrDocument, IrRegion, ProducerMetadata};
use tree_sitter::Parser;

use super::PythonExtractError;

const PYTHON_GRAMMAR_VERSION: &str = "0.25.0";

/// Parse UTF-8 Python source with the vendored tree-sitter grammar.
///
/// Returns the concrete syntax tree for `source`. Grammar installation
/// failures map to `GrammarLoad`; a parser refusal to produce a tree maps to
/// `NoParseTree`.
pub(super) fn parse_python(source: &str) -> Result<tree_sitter::Tree, PythonExtractError> {
    let mut parser = Parser::new();
    let language = tree_sitter_python::LANGUAGE.into();
    parser
        .set_language(&language)
        .map_err(|_| PythonExtractError::GrammarLoad)?;
    parser
        .parse(source, None)
        .ok_or(PythonExtractError::NoParseTree)
}

/// Build producer metadata for Python docstring IR.
///
/// The options record the extractor contract: docstring content is emitted
/// verbatim from source spans, the node store is bounded to module, owner, and
/// docstring nodes, and qualified names follow Python's `__qualname__`
/// convention.
pub(super) fn python_producer() -> ProducerMetadata {
    let mut options = BTreeMap::new();
    options.insert(
        "docstring_content".to_owned(),
        serde_json::json!("verbatim"),
    );
    options.insert("node_store".to_owned(), serde_json::json!("bounded"));
    options.insert("owner_qualname".to_owned(), serde_json::json!("python"));
    ProducerMetadata {
        kind: "tree-sitter".to_owned(),
        name: "tree-sitter-python".to_owned(),
        version: PYTHON_GRAMMAR_VERSION.to_owned(),
        options,
    }
}

/// Validate Python IR consistency in debug builds.
///
/// Checks that the document content hash and line index match the source text
/// and that every region's segments reconstruct the extracted text.
pub(super) fn validate_ir_consistency(document: &IrDocument, source: &str) {
    debug_assert_eq!(
        document.document.content_hash,
        stilyagi_ir::content_hash_for(source)
    );
    debug_assert_eq!(document.line_index, stilyagi_ir::line_index_for(source));
    debug_assert!(
        document
            .regions
            .iter()
            .all(IrRegion::segments_reconstruct_text)
    );
}

#[cfg(test)]
mod tests {
    //! Regression guard keeping the grammar version metadata pinned in step
    //! with the `tree-sitter-python` dependency.

    use super::PYTHON_GRAMMAR_VERSION;

    #[test]
    fn python_grammar_version_matches_the_pinned_dependency() {
        let manifest = stilyagi_test_fixtures::read_corpus_fixture("Cargo.toml")
            .expect("workspace manifest should be readable");
        let pinned = manifest
            .lines()
            .find(|line| line.trim_start().starts_with("tree-sitter-python "))
            .and_then(|line| line.split('"').nth(1))
            .expect("tree-sitter-python should be pinned in the workspace manifest");

        assert_eq!(
            pinned, PYTHON_GRAMMAR_VERSION,
            "PYTHON_GRAMMAR_VERSION must match the pinned tree-sitter-python version"
        );
    }
}
