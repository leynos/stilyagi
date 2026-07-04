//! Shared test helpers for `stilyagi-extract` integration tests.

use rstest::fixture;
use stilyagi_extract::{
    ExtractDocument, ExtractError, ExtractSyntax, SourceIdentity, extract_document,
    extract_document_with_source_identity,
};
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

pub(crate) const SHARED_PYTHON_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/python/valid/module-class-function-docstrings.py";
pub(crate) const SHARED_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/item-doc-comments.rs";
pub(crate) const MALFORMED_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/malformed/unclosed-item.rs";
pub(crate) const NESTED_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/nested-modules-impls.rs";
pub(crate) const MULTILINE_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/doc-comment-multiline.rs";

pub(crate) fn boundary() -> stilyagi_extract::ExtractBoundary {
    stilyagi_extract::ExtractBoundary::default()
}

pub(crate) fn must_extract_document(source: &str, syntax: ExtractSyntax) -> ExtractDocument {
    match extract_document(source, syntax) {
        Ok(document) => document,
        Err(error) => panic!("expected successful extraction: {error}"),
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

#[fixture]
pub(crate) fn shared_python_source() -> String {
    match read_corpus_fixture(SHARED_PYTHON_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected shared Python corpus fixture to be readable: {error}"),
    }
}

#[fixture]
pub(crate) fn shared_rust_source() -> String {
    match read_corpus_fixture(SHARED_RUST_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected shared Rust corpus fixture to be readable: {error}"),
    }
}

#[fixture]
pub(crate) fn malformed_rust_source() -> String {
    match read_corpus_fixture(MALFORMED_RUST_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected malformed Rust corpus fixture to be readable: {error}"),
    }
}

#[fixture]
pub(crate) fn nested_rust_source() -> String {
    match read_corpus_fixture(NESTED_RUST_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected nested Rust corpus fixture to be readable: {error}"),
    }
}

#[fixture]
pub(crate) fn multiline_rust_source() -> String {
    match read_corpus_fixture(MULTILINE_RUST_FIXTURE_PATH) {
        Ok(source) => source,
        Err(error) => panic!("expected multiline Rust corpus fixture to be readable: {error}"),
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
