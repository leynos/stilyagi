//! Shared, fallible helpers for the tree-sitter extraction test suites.
//!
//! Nothing in this module panics. Extraction and fixture reads return
//! `Result`, and tree queries return `Option` or a plain collection, so each
//! test decides how a missing precondition should be reported. Tests either
//! `.expect(...)` at the boundary or use the assertion macros exported here,
//! which expand at the call site so failures point at the calling test.

use stilyagi_ir::{IrDocument, IrRegion, SourceIdentity};
use stilyagi_test_fixtures::read_corpus_fixture;
use tree_sitter::{Language, Node, Parser, Tree};

use crate::python::types::NodeKind;
use crate::{
    PythonExtractError, RustExtractError, python_docstring_ir_document,
    rust_doc_comment_ir_document,
};

impl From<&'static str> for NodeKind {
    fn from(kind: &'static str) -> Self {
        Self(kind)
    }
}

/// Parse Rust source with the vendored `tree-sitter-rust` grammar.
pub(crate) fn parse_rust_source(source: &str) -> Result<Tree, String> {
    let language: Language = tree_sitter_rust::LANGUAGE.into();

    parse_source(&language, source, "tree-sitter-rust")
}

/// Parse Python source with the vendored `tree-sitter-python` grammar.
pub(crate) fn parse_python_source(source: &str) -> Result<Tree, String> {
    let language: Language = tree_sitter_python::LANGUAGE.into();

    parse_source(&language, source, "tree-sitter-python")
}

fn parse_source(language: &Language, source: &str, grammar: &str) -> Result<Tree, String> {
    let mut parser = Parser::new();
    parser
        .set_language(language)
        .map_err(|error| format!("{grammar} grammar should load: {error}"))?;
    parser
        .parse(source, None)
        .ok_or_else(|| format!("{grammar} should return a parse tree"))
}

/// Return the first named child of `node`, if it has one.
pub(crate) fn first_named_child(node: Node<'_>) -> Option<Node<'_>> {
    node.named_child(0)
}

/// Return the first direct named child of `node` whose kind is `kind`.
pub(crate) fn direct_named_child_with_kind(
    node: Node<'_>,
    kind: impl Into<NodeKind>,
) -> Option<Node<'_>> {
    let wanted = kind.into();
    let mut cursor = node.walk();

    node.named_children(&mut cursor)
        .find(|child| child.kind() == wanted.as_str())
}

/// Return every direct named child of `node` whose kind is `kind`.
pub(crate) fn named_children_with_kind(node: Node<'_>, kind: impl Into<NodeKind>) -> Vec<Node<'_>> {
    let wanted = kind.into();
    let mut cursor = node.walk();

    node.named_children(&mut cursor)
        .filter(|child| child.kind() == wanted.as_str())
        .collect()
}

/// Return every named descendant of `node` whose kind is `kind`.
///
/// Descendants are returned in document order, so `.into_iter().next()` yields
/// the first match.
pub(crate) fn descendants_with_kind(node: Node<'_>, kind: impl Into<NodeKind>) -> Vec<Node<'_>> {
    let wanted = kind.into();
    let mut found = Vec::new();
    collect_descendants_with_kind(node, wanted, &mut found);
    found
}

fn collect_descendants_with_kind<'tree>(
    node: Node<'tree>,
    kind: NodeKind,
    found: &mut Vec<Node<'tree>>,
) {
    let mut cursor = node.walk();

    for child in node.named_children(&mut cursor) {
        if child.kind() == kind.as_str() {
            found.push(child);
        }
        collect_descendants_with_kind(child, kind, found);
    }
}

/// Return the source text spanned by `node`.
pub(crate) fn text_for_node<'source>(
    source: &'source str,
    node: Node<'_>,
) -> Result<&'source str, std::str::Utf8Error> {
    node.utf8_text(source.as_bytes())
}

/// Assert that the first named child of a node has the expected kind.
///
/// The query and the assertion both expand at the call site, so a failure
/// reports the calling test's line rather than a shared helper's.
macro_rules! assert_first_named_child_kind {
    ($node:expr, $kind:expr) => {{
        let expected_kind = $crate::python::types::NodeKind::from($kind);
        let named_child = $crate::test_support::first_named_child($node)
            .expect("node should have a first named child");

        assert_eq!(named_child.kind(), expected_kind.as_str());
        named_child
    }};
}

pub(crate) use assert_first_named_child_kind;

/// A source-backed segment whose recorded text disagrees with the source.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct SegmentMismatch {
    /// Byte span recorded on the segment.
    pub span: (usize, usize),
    /// Text the segment claims to cover.
    pub expected: String,
    /// Text the source holds at `span`, or `None` when the span is out of
    /// bounds or splits a character boundary.
    pub actual: Option<String>,
}

/// Collect every source-backed segment whose text disagrees with `source`.
///
/// Returning the full mismatch list rather than asserting per segment lets a
/// failing test report every disagreement at once.
pub(crate) fn source_backed_segment_mismatches(
    document: &IrDocument,
    source: &str,
) -> Vec<SegmentMismatch> {
    document
        .regions
        .iter()
        .flat_map(|region| region.segments.iter())
        .filter_map(|segment| {
            let span = segment.source?;
            let actual = source.get(span.byte_start..span.byte_end);
            (actual != Some(segment.text.as_str())).then(|| SegmentMismatch {
                span: (span.byte_start, span.byte_end),
                expected: segment.text.clone(),
                actual: actual.map(ToOwned::to_owned),
            })
        })
        .collect()
}

/// Assert that every source-backed segment matches the corresponding source
/// bytes, listing all mismatches when the check fails.
macro_rules! assert_segments_match_source {
    ($document:expr, $source:expr) => {{
        let mismatches = $crate::test_support::source_backed_segment_mismatches($document, $source);

        assert!(
            mismatches.is_empty(),
            "source-backed segments should match the source bytes: {mismatches:?}"
        );
    }};
}

pub(crate) use assert_segments_match_source;

/// Owner metadata projected from a region: kind, name, and qualified name.
pub(crate) type OwnerTriple<'region> = (&'region str, Option<&'region str>, Option<&'region str>);

/// Region text projected alongside its owner metadata.
pub(crate) type RegionOwner<'region> = (
    &'region str,
    &'region str,
    Option<&'region str>,
    Option<&'region str>,
);

/// Project a region's owner metadata, if the region has an owner.
pub(crate) fn owner_triple(region: &IrRegion) -> Option<OwnerTriple<'_>> {
    let owner = region.owner.as_ref()?;

    Some((
        owner.kind.as_str(),
        owner.name.as_deref(),
        owner.qualname.as_deref(),
    ))
}

/// Project every region's text alongside its owner metadata.
///
/// Returns `None` when any region lacks owner metadata, so callers can treat a
/// missing owner as a test failure at the boundary.
pub(crate) fn region_owners(document: &IrDocument) -> Option<Vec<RegionOwner<'_>>> {
    document
        .regions
        .iter()
        .map(|region| {
            let (kind, name, qualname) = owner_triple(region)?;
            Some((region.text.as_str(), kind, name, qualname))
        })
        .collect()
}

/// Extract Rust doc-comment IR for anonymous source.
pub(crate) fn extract_rust(source: &str) -> Result<IrDocument, RustExtractError> {
    rust_doc_comment_ir_document(source, SourceIdentity::anonymous())
}

/// Extract Python docstring IR for anonymous source.
pub(crate) fn extract_python(source: &str) -> Result<IrDocument, PythonExtractError> {
    python_docstring_ir_document(source, SourceIdentity::anonymous())
}

/// Read a corpus fixture and extract Rust doc-comment IR from it.
pub(crate) fn rust_fixture_document(path: &str) -> Result<IrDocument, String> {
    fixture_document(path, |source| {
        extract_rust(source).map_err(|error| format!("expected Rust extraction: {error}"))
    })
}

/// Read a corpus fixture and extract Python docstring IR from it.
pub(crate) fn python_fixture_document(path: &str) -> Result<IrDocument, String> {
    fixture_document(path, |source| {
        extract_python(source).map_err(|error| format!("expected Python extraction: {error}"))
    })
}

fn fixture_document(
    path: &str,
    extract: impl FnOnce(&str) -> Result<IrDocument, String>,
) -> Result<IrDocument, String> {
    let source =
        read_corpus_fixture(path).map_err(|error| format!("expected fixture {path}: {error}"))?;

    extract(&source)
}
