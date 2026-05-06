//! Source extraction orchestration for the first Rust-to-Python bridge.

use core::fmt;
use stilyagi_ir::IrBoundary;
use stilyagi_markdown::MarkdownBoundary;
use stilyagi_tree_sitter::TreeSitterBoundary;

/// Supported source syntaxes for the initial extraction boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExtractSyntax {
    /// Markdown prose extracted directly from `.md` sources.
    Markdown,
    /// Python docstring extraction, reserved for a later roadmap slice.
    PythonDocstring,
    /// Rust documentation-comment extraction, reserved for a later slice.
    RustDocComment,
}

impl ExtractSyntax {
    /// Ordered list of the stable syntax spellings exposed through the bridge.
    pub const ALL: [Self; 3] = [Self::Markdown, Self::PythonDocstring, Self::RustDocComment];

    /// Return the stable Python-facing syntax spelling.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Markdown => "markdown",
            Self::PythonDocstring => "python_docstring",
            Self::RustDocComment => "rust_doc_comment",
        }
    }
}

impl fmt::Display for ExtractSyntax {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Extraction failures surfaced by the narrow v1 bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExtractError {
    /// The requested syntax is part of the long-term model, but not yet
    /// implemented by the extractor.
    UnsupportedSyntax(ExtractSyntax),
    /// The caller provided a syntax name that is not part of the supported
    /// syntax vocabulary.
    UnknownSyntax(String),
}

impl fmt::Display for ExtractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedSyntax(syntax) => {
                write!(formatter, "{syntax} extraction is not implemented yet.")
            }
            Self::UnknownSyntax(syntax) => {
                write!(formatter, "unknown syntax '{syntax}'")
            }
        }
    }
}

impl std::error::Error for ExtractError {}

impl TryFrom<&str> for ExtractSyntax {
    type Error = ExtractError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "markdown" => Ok(Self::Markdown),
            "python_docstring" => Ok(Self::PythonDocstring),
            "rust_doc_comment" => Ok(Self::RustDocComment),
            _ => Err(ExtractError::UnknownSyntax(value.to_owned())),
        }
    }
}

/// Stable kind names for extracted prose regions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegionKind {
    /// Whole-document prose extracted from a source file.
    Document,
}

impl RegionKind {
    /// Return the stable bridge spelling for this region kind.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Document => "document",
        }
    }
}

impl fmt::Display for RegionKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Minimal source-backed prose region for the first extraction bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractRegion {
    kind: RegionKind,
    text: String,
}

impl ExtractRegion {
    /// Create a region with the supplied stable kind name and text.
    #[must_use]
    pub fn new(kind: RegionKind, text: impl Into<String>) -> Self {
        Self {
            kind,
            text: text.into(),
        }
    }

    /// Return the stable region kind name.
    #[must_use]
    pub const fn kind(&self) -> RegionKind {
        self.kind
    }

    /// Return the extracted region text.
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}

/// Partial document payload returned by the first extraction slice.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractDocument {
    syntax: ExtractSyntax,
    regions: Vec<ExtractRegion>,
}

impl ExtractDocument {
    /// Create a partial document with the supplied syntax and regions.
    #[must_use]
    pub const fn new(syntax: ExtractSyntax, regions: Vec<ExtractRegion>) -> Self {
        Self { syntax, regions }
    }

    /// Return the syntax represented by the document.
    #[must_use]
    pub const fn syntax(&self) -> ExtractSyntax {
        self.syntax
    }

    /// Return the extracted prose regions.
    #[must_use]
    pub fn regions(&self) -> &[ExtractRegion] {
        &self.regions
    }
}

/// Marker type for the future extraction orchestration boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ExtractBoundary {
    /// Placeholder for Markdown extraction support.
    markdown: MarkdownBoundary,
    /// Placeholder for tree-sitter extraction support.
    tree_sitter: TreeSitterBoundary,
    /// Placeholder for IR construction support.
    ir: IrBoundary,
}

impl ExtractBoundary {
    /// Return the placeholder Markdown extraction boundary.
    #[must_use]
    pub const fn markdown(&self) -> &MarkdownBoundary {
        &self.markdown
    }

    /// Return the placeholder tree-sitter extraction boundary.
    #[must_use]
    pub const fn tree_sitter(&self) -> &TreeSitterBoundary {
        &self.tree_sitter
    }

    /// Return the placeholder IR construction boundary.
    #[must_use]
    pub const fn ir(&self) -> &IrBoundary {
        &self.ir
    }
}

/// Extract a minimal document-shaped payload for the supported syntax.
///
/// # Errors
///
/// Returns [`ExtractError::UnsupportedSyntax`] when the syntax is part of the
/// current model vocabulary but not yet implemented. Returns
/// [`ExtractError::UnknownSyntax`] only when a caller first converts an
/// arbitrary string into [`ExtractSyntax`] via `TryFrom<&str>`.
pub fn extract_document(
    source: &str,
    syntax: ExtractSyntax,
) -> Result<ExtractDocument, ExtractError> {
    match syntax {
        ExtractSyntax::Markdown => Ok(extract_markdown_document(source)),
        ExtractSyntax::PythonDocstring | ExtractSyntax::RustDocComment => {
            Err(ExtractError::UnsupportedSyntax(syntax))
        }
    }
}

fn extract_markdown_document(source: &str) -> ExtractDocument {
    let regions = if source.trim().is_empty() {
        Vec::new()
    } else {
        vec![ExtractRegion::new(RegionKind::Document, source)]
    };
    ExtractDocument::new(ExtractSyntax::Markdown, regions)
}

#[cfg(test)]
mod tests {
    use super::{
        ExtractBoundary, ExtractDocument, ExtractError, ExtractRegion, ExtractSyntax, RegionKind,
        extract_document,
    };
    use rstest::{fixture, rstest};
    use std::path::PathBuf;
    use stilyagi_ir::IrBoundary;
    use stilyagi_markdown::MarkdownBoundary;
    use stilyagi_tree_sitter::TreeSitterBoundary;

    const SHARED_MARKDOWN_FIXTURE: &str =
        "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md";

    fn repository_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(std::path::Path::parent)
            .map_or_else(PathBuf::new, std::path::Path::to_path_buf)
    }

    fn corpus_fixture_path(relative_path: impl AsRef<std::path::Path>) -> PathBuf {
        repository_root().join(relative_path)
    }

    fn read_corpus_fixture(
        relative_path: impl AsRef<std::path::Path>,
    ) -> Result<String, std::io::Error> {
        std::fs::read_to_string(corpus_fixture_path(relative_path))
    }

    /// Keep the extraction boundary default stable and comparable.
    #[test]
    fn extract_boundary_default_matches_another_default() {
        assert_eq!(ExtractBoundary::default(), ExtractBoundary::default());
    }

    /// Keep the marker accessors wired to the corresponding boundary defaults.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the marker Default implementations"
    )]
    fn extract_boundary_accessors_expose_the_expected_markers() {
        let boundary = ExtractBoundary::default();

        assert_eq!(boundary.markdown(), &MarkdownBoundary::default());
        assert_eq!(boundary.tree_sitter(), &TreeSitterBoundary::default());
        assert_eq!(boundary.ir(), &IrBoundary::default());
    }

    /// Keep the extraction boundary copy semantics available to callers.
    #[test]
    fn extract_boundary_is_copy() {
        let original = ExtractBoundary::default();
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first.markdown(), second.markdown());
        assert_eq!(first.tree_sitter(), second.tree_sitter());
        assert_eq!(first.ir(), second.ir());
    }

    /// Keep the extraction boundary debug output identifiable in failures.
    #[test]
    fn extract_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{:?}", ExtractBoundary::default()).contains("ExtractBoundary"));
    }

    #[expect(
        clippy::expect_used,
        reason = "test helper should fail loudly when a supported extraction path breaks"
    )]
    fn must_extract_document(source: &str, syntax: ExtractSyntax) -> ExtractDocument {
        extract_document(source, syntax).expect("expected successful extraction")
    }

    #[expect(
        clippy::expect_used,
        reason = "test helper should fail loudly when an unsupported extraction unexpectedly succeeds"
    )]
    fn must_reject_document(source: &str, syntax: ExtractSyntax) -> ExtractError {
        extract_document(source, syntax).expect_err("expected extraction failure")
    }

    #[expect(
        clippy::expect_used,
        reason = "test helper should fail loudly when invalid syntax conversion unexpectedly succeeds"
    )]
    fn must_reject_syntax_name(input: &str) -> ExtractError {
        ExtractSyntax::try_from(input).expect_err("expected unknown syntax error")
    }

    #[fixture]
    fn extracted_markdown() -> ExtractDocument {
        must_extract_document("# Heading", ExtractSyntax::Markdown)
    }

    #[fixture]
    fn extracted_blank_markdown_documents() -> Vec<ExtractDocument> {
        ["", "   \n\t"]
            .into_iter()
            .map(|source| must_extract_document(source, ExtractSyntax::Markdown))
            .collect()
    }

    #[fixture]
    fn extracted_unicode_markdown() -> ExtractDocument {
        must_extract_document("Zażółć gęślą jaźń 🫖", ExtractSyntax::Markdown)
    }

    #[fixture]
    fn shared_markdown_source() -> String {
        read_corpus_fixture(SHARED_MARKDOWN_FIXTURE).unwrap_or_else(|error| {
            panic!("expected shared Markdown corpus fixture to be readable: {error}")
        })
    }

    /// Keep the first extraction bridge pinned to Markdown for the initial
    /// vertical slice.
    #[rstest]
    fn markdown_extraction_reports_markdown_syntax(extracted_markdown: ExtractDocument) {
        assert_eq!(extracted_markdown.syntax(), ExtractSyntax::Markdown);
    }

    /// Keep blank Markdown extraction honest instead of synthesizing placeholder
    /// prose that does not exist in the source.
    #[rstest]
    fn blank_markdown_extraction_yields_no_regions(
        extracted_blank_markdown_documents: Vec<ExtractDocument>,
    ) {
        for document in extracted_blank_markdown_documents {
            assert!(document.regions().is_empty());
        }
    }

    /// Keep the first end-to-end bridge narrow by returning one source-faithful
    /// region for non-empty Markdown.
    #[rstest]
    fn non_blank_markdown_extraction_yields_one_document_region(
        extracted_markdown: ExtractDocument,
    ) {
        assert_eq!(extracted_markdown.regions().len(), 1);
        let first_region = extracted_markdown.regions().first();

        assert_eq!(
            first_region.map(ExtractRegion::kind),
            Some(RegionKind::Document)
        );
        assert_eq!(first_region.map(ExtractRegion::text), Some("# Heading"));
    }

    /// Preserve Unicode content across the extraction boundary so later rule
    /// layers can rely on source-faithful text.
    #[rstest]
    fn markdown_extraction_preserves_unicode_text(extracted_unicode_markdown: ExtractDocument) {
        let first_region = extracted_unicode_markdown.regions().first();

        assert_eq!(
            first_region.map(ExtractRegion::text),
            Some("Zażółć gęślą jaźń 🫖")
        );
    }

    /// Anchor Markdown extraction tests to the shared source corpus instead of
    /// relying only on inline strings.
    #[rstest]
    fn markdown_extraction_preserves_the_shared_markdown_fixture(shared_markdown_source: String) {
        let document = must_extract_document(&shared_markdown_source, ExtractSyntax::Markdown);
        let first_region = document.regions().first();

        assert_eq!(document.syntax(), ExtractSyntax::Markdown);
        assert_eq!(
            first_region.map(ExtractRegion::kind),
            Some(RegionKind::Document)
        );
        assert_eq!(
            first_region.map(ExtractRegion::text),
            Some(shared_markdown_source.as_str()),
        );
    }

    /// Keep malformed corpus inputs loadable without promising parser recovery
    /// semantics that belong to later extraction work.
    #[rstest]
    #[case("tests/fixtures/corpus/markdown/malformed/unclosed-table.md")]
    #[case("tests/fixtures/corpus/python/malformed/unclosed-function.py.txt")]
    #[case("tests/fixtures/corpus/rust/malformed/unclosed-item.rs")]
    fn malformed_corpus_fixtures_are_readable_utf8_sources(#[case] relative_path: &str) {
        let source = read_corpus_fixture(relative_path)
            .unwrap_or_else(|error| panic!("expected readable fixture {relative_path}: {error}"));

        assert!(!source.is_empty());
    }

    /// Reject unsupported syntaxes explicitly so the Python layer can map the
    /// failure to a user-facing `NotImplementedError`.
    #[rstest]
    #[case(ExtractSyntax::PythonDocstring)]
    #[case(ExtractSyntax::RustDocComment)]
    fn unsupported_syntaxes_are_rejected(#[case] syntax: ExtractSyntax) {
        let error = must_reject_document("example", syntax);

        assert_eq!(error, ExtractError::UnsupportedSyntax(syntax));
    }

    /// Keep the stable spelling of each syntax variant accessible to callers.
    #[rstest]
    #[case(ExtractSyntax::Markdown, "markdown")]
    #[case(ExtractSyntax::PythonDocstring, "python_docstring")]
    #[case(ExtractSyntax::RustDocComment, "rust_doc_comment")]
    fn syntax_as_str_returns_the_expected_spelling(
        #[case] syntax: ExtractSyntax,
        #[case] expected: &str,
    ) {
        assert_eq!(syntax.as_str(), expected);
    }

    /// Keep the Display output for each syntax variant identical to `as_str`.
    #[rstest]
    #[case(ExtractSyntax::Markdown, "markdown")]
    #[case(ExtractSyntax::PythonDocstring, "python_docstring")]
    #[case(ExtractSyntax::RustDocComment, "rust_doc_comment")]
    fn syntax_display_matches_as_str(#[case] syntax: ExtractSyntax, #[case] expected: &str) {
        assert_eq!(format!("{syntax}"), expected);
    }

    /// Keep the stable spelling of each region kind accessible to callers.
    #[rstest]
    #[case(RegionKind::Document, "document")]
    fn region_kind_as_str_returns_the_expected_spelling(
        #[case] kind: RegionKind,
        #[case] expected: &str,
    ) {
        assert_eq!(kind.as_str(), expected);
    }

    /// Keep the Display output for each region kind identical to `as_str`.
    #[rstest]
    #[case(RegionKind::Document, "document")]
    fn region_kind_display_matches_as_str(#[case] kind: RegionKind, #[case] expected: &str) {
        assert_eq!(format!("{kind}"), expected);
    }

    /// Keep the Display output for each error variant informative and stable.
    #[rstest]
    #[case(
        ExtractError::UnsupportedSyntax(ExtractSyntax::PythonDocstring),
        "python_docstring extraction is not implemented yet."
    )]
    #[case(
        ExtractError::UnknownSyntax("bogus".to_owned()),
        "unknown syntax 'bogus'"
    )]
    fn extract_error_display_is_informative(#[case] error: ExtractError, #[case] expected: &str) {
        assert_eq!(format!("{error}"), expected);
    }

    /// Keep `TryFrom<&str>` honest by rejecting unrecognised syntax names.
    #[rstest]
    #[case("totally_invalid")]
    #[case("")]
    #[case("MARKDOWN")]
    fn try_from_str_rejects_unknown_syntax(#[case] input: &str) {
        let error = must_reject_syntax_name(input);
        assert!(matches!(error, ExtractError::UnknownSyntax(_)));
        assert!(error.to_string().contains(input) || input.is_empty());
    }
}
