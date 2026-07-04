//! Rust documentation-comment extraction backed by `tree-sitter-rust`.

mod builder;
mod builder_state;
mod helpers;
mod observe;
mod owner;
mod support;
pub(super) mod types;

use stilyagi_ir::{DocumentMetadata, IrDocument, IrTree, SourceIdentity};

use builder::RustIrBuilder;
use observe::{record_extraction_outcome, record_fatal_error};
use support::{parse_rust, rust_producer, validate_ir_consistency};

const TREE_ID: &str = "t0";

/// Maximum concrete-syntax-tree depth walked during doc-comment extraction.
const MAX_TRAVERSAL_DEPTH: usize = 256;

/// Fatal failure while building Rust doc-comment IR.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RustExtractError {
    /// The Rust grammar failed to load into the parser.
    GrammarLoad,
    /// tree-sitter returned no parse tree for the source.
    NoParseTree,
}

impl RustExtractError {
    /// Stable, low-cardinality category label for logs and metrics.
    const fn category(self) -> &'static str {
        match self {
            Self::GrammarLoad => "grammar_load",
            Self::NoParseTree => "no_parse_tree",
        }
    }
}

impl std::fmt::Display for RustExtractError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::GrammarLoad => formatter.write_str("failed to load tree-sitter-rust grammar"),
            Self::NoParseTree => formatter.write_str("tree-sitter returned no Rust parse tree"),
        }
    }
}

impl std::error::Error for RustExtractError {}

/// Build an owner-aware Rust doc-comment IR document.
///
/// # Errors
///
/// Returns a fatal extraction error only when the grammar cannot be loaded or
/// no parse tree can be produced. Recoverable parse anomalies belong in the IR
/// document `errors` list.
#[tracing::instrument(
    name = "rust_doc_comment_extraction",
    skip(source, identity),
    fields(syntax = "rust", source_len = source.len())
)]
pub fn rust_doc_comment_ir_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<IrDocument, RustExtractError> {
    metrics::counter!("stilyagi_rust_extraction_documents_total").increment(1);
    let tree = parse_rust(source).inspect_err(|error| record_fatal_error(*error))?;
    let root = tree.root_node();
    let mut document = IrDocument::empty(
        DocumentMetadata::new("rust", identity.path, identity.uri, source),
        vec![rust_producer()],
        source,
    );
    document.trees.push(IrTree {
        id: TREE_ID.to_owned(),
        family: "tree-sitter".to_owned(),
        syntax: "rust".to_owned(),
        root: root_node_id().into(),
    });

    let mut builder = RustIrBuilder::new(source);
    builder.push_module_root(root);
    builder.push_recovery_errors(root);
    builder.visit_container(root, &mut Vec::new(), 0);

    let (nodes, regions, errors) = builder.into_ir();
    document.nodes = nodes;
    document.regions = regions;
    document.errors = errors;
    validate_ir_consistency(&document, source);
    record_extraction_outcome(&document);
    Ok(document)
}

fn root_node_id() -> types::NodeId {
    types::NodeId("n0".to_owned())
}

#[cfg(test)]
mod source_oracle_tests;

#[cfg(test)]
mod tests;
