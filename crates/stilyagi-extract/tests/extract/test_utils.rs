//! Shared test helpers for `stilyagi-extract` integration tests.

use rstest::fixture;
use stilyagi_extract::{
    ExtractDocument, ExtractError, ExtractSyntax, SourceIdentity, extract_document,
    extract_document_with_source_identity,
};
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

pub(crate) fn boundary() -> stilyagi_extract::ExtractBoundary {
    stilyagi_extract::ExtractBoundary::default()
}

pub(crate) fn must_extract_document(source: &str, syntax: ExtractSyntax) -> ExtractDocument {
    match extract_document(source, syntax) {
        Ok(document) => document,
        Err(error) => panic!("expected successful extraction: {error}"),
    }
}

pub(crate) fn must_reject_document(source: &str, syntax: ExtractSyntax) -> ExtractError {
    match extract_document(source, syntax) {
        Ok(value) => {
            panic!("expected extraction failure; got success: {value:?}");
        }
        Err(error) => error,
    }
}

pub(crate) fn must_reject_syntax_name(input: &str) -> ExtractError {
    match ExtractSyntax::try_from(input) {
        Ok(syntax) => panic!("expected unknown syntax error; got: {syntax}"),
        Err(error) => error,
    }
}

#[fixture]
pub(crate) fn extracted_markdown() -> ExtractDocument {
    must_extract_document("# Heading", ExtractSyntax::Markdown)
}

#[fixture]
pub(crate) fn extracted_blank_markdown_documents() -> Vec<ExtractDocument> {
    ["", "   \n\t"]
        .into_iter()
        .map(|source| must_extract_document(source, ExtractSyntax::Markdown))
        .collect()
}

#[fixture]
pub(crate) fn extracted_unicode_markdown() -> ExtractDocument {
    must_extract_document("Zażółć gęślą jaźń 🫖", ExtractSyntax::Markdown)
}

#[fixture]
pub(crate) fn shared_markdown_source() -> String {
    match read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected shared Markdown corpus fixture to be readable: {error}"),
    }
}

pub(crate) fn markdown_extraction_with_identity(
    source: &str,
    identity: SourceIdentity,
) -> ExtractDocument {
    match extract_document_with_source_identity(source, ExtractSyntax::Markdown, identity) {
        Ok(document) => document,
        Err(error) => panic!("expected markdown extraction with explicit identity: {error}"),
    }
}
