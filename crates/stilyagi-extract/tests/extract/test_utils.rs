//! Shared test helpers for `stilyagi-extract` integration tests.
//!
//! Setup helpers and rstest fixtures here are fallible: they return the
//! underlying error so that recognized test bodies decide how to fail.

use rstest::fixture;
use stilyagi_extract::{
    ExtractDocument, ExtractError, ExtractSyntax, SourceIdentity, extract_document,
    extract_document_with_source_identity,
};
use stilyagi_test_support::{
    FixtureReadError, SHARED_MARKDOWN_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH,
    SHARED_RUST_FIXTURE_PATH, read_corpus_fixture,
};

/// Outcome of reading a corpus fixture, handed to tests as a fixture value.
pub(crate) type FixtureSource = Result<String, FixtureReadError>;

pub(crate) fn boundary() -> stilyagi_extract::ExtractBoundary {
    stilyagi_extract::ExtractBoundary::default()
}

/// Returns the rejection error, or `None` when the syntax name was accepted.
pub(crate) fn syntax_name_rejection(input: &str) -> Option<ExtractError> {
    ExtractSyntax::try_from(input).err()
}

#[fixture]
pub(crate) fn extracted_markdown() -> Result<ExtractDocument, ExtractError> {
    extract_document("# Heading", ExtractSyntax::Markdown)
}

#[fixture]
pub(crate) fn extracted_blank_markdown_documents() -> Result<Vec<ExtractDocument>, ExtractError> {
    ["", "   \n\t"]
        .into_iter()
        .map(|source| extract_document(source, ExtractSyntax::Markdown))
        .collect()
}

#[fixture]
pub(crate) fn extracted_unicode_markdown() -> Result<ExtractDocument, ExtractError> {
    extract_document("Zażółć gęślą jaźń 🫖", ExtractSyntax::Markdown)
}

#[fixture]
pub(crate) fn shared_markdown_source() -> FixtureSource {
    read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
}

#[fixture]
pub(crate) fn shared_python_source() -> FixtureSource {
    read_corpus_fixture(SHARED_PYTHON_FIXTURE_PATH)
}

#[fixture]
pub(crate) fn shared_rust_source() -> FixtureSource {
    read_corpus_fixture(SHARED_RUST_FIXTURE_PATH)
}

pub(crate) fn markdown_extraction_with_identity(
    source: &str,
    identity: SourceIdentity,
) -> Result<ExtractDocument, ExtractError> {
    extract_document_with_source_identity(source, ExtractSyntax::Markdown, identity)
}
