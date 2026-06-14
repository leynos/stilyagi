//! Tests for recovered and adversarial Markdown fixture extraction.

use std::fs;

use rstest::rstest;
use stilyagi_ir::{IrDocument, RegionKind};
use stilyagi_test_support::{corpus_fixture_path, read_corpus_fixture};

use super::{
    parent_regions_reference_earlier_regions, region_segments_are_contiguous,
    regions_reconstruct_text, source_backed_segments_match_source, source_identity,
    synthetic_segments_use_known_reasons,
};
use crate::markdown_ir_document;

#[rstest]
#[case::unclosed_table(
    "tests/fixtures/corpus/markdown/malformed/unclosed-table.md",
    "malformed_unclosed_table"
)]
#[case::unbalanced_emphasis(
    "tests/fixtures/corpus/markdown/malformed/unbalanced-emphasis.md.fixture",
    "malformed_unbalanced_emphasis"
)]
#[case::broken_reference_link(
    "tests/fixtures/corpus/markdown/malformed/broken-reference-link.md.fixture",
    "malformed_broken_reference_link"
)]
fn malformed_markdown_recovers_to_reviewed_degraded_regions(
    #[case] relative_path: &str,
    #[case] snapshot_name: &str,
) {
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected malformed Markdown fixture: {error}"));
    let document = document_for(relative_path, &source);
    let json = document
        .to_canonical_json()
        .unwrap_or_else(|error| panic!("expected canonical JSON: {error}"));
    let parsed = serde_json::from_str::<IrDocument>(&json)
        .unwrap_or_else(|error| panic!("expected canonical JSON round-trip: {error}"));

    assert_eq!(parsed, document);
    assert!(regions_reconstruct_text(&document));
    assert!(region_segments_are_contiguous(&document));
    assert!(source_backed_segments_match_source(&document, &source));
    assert!(synthetic_segments_use_known_reasons(&document));
    assert!(parent_regions_reference_earlier_regions(&document));
    // Suppression parsing and non-fatal error emission belong to roadmap item
    // 2.1.3, so parser recovery must not fabricate IR errors in this slice.
    assert!(document.errors.is_empty());
    insta::assert_snapshot!(snapshot_name, degraded_region_text(&document));
}

#[rstest]
#[case::list("tests/fixtures/corpus/markdown/valid/list-crlf.md.fixture")]
#[case::blockquote("tests/fixtures/corpus/markdown/valid/blockquote-crlf.md.fixture")]
fn crlf_structural_fixtures_contain_literal_crlf_bytes(#[case] relative_path: &str) {
    let path = corpus_fixture_path(relative_path)
        .unwrap_or_else(|error| panic!("expected CRLF fixture path: {error}"));
    let bytes =
        fs::read(path).unwrap_or_else(|error| panic!("expected readable fixture bytes: {error}"));

    assert!(bytes.windows(2).any(|pair| pair == b"\r\n"));
}

#[rstest]
fn deeply_nested_blockquote_keeps_well_formed_parent_chain() {
    let relative_path = "tests/fixtures/corpus/markdown/valid/deep-blockquote.md.fixture";
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected deep blockquote fixture: {error}"));
    let document = document_for(relative_path, &source);
    let blockquotes = document
        .regions
        .iter()
        .filter(|region| region.kind == RegionKind::Blockquote.as_str())
        .collect::<Vec<_>>();

    assert_eq!(blockquotes.len(), 8);
    assert!(parent_regions_reference_earlier_regions(&document));
    assert!(blockquotes.iter().all(|region| region.text.is_empty()));
    assert!(
        document
            .regions
            .iter()
            .any(|region| region.text == "Eight levels deep.")
    );
}

#[rstest]
fn empty_list_item_does_not_emit_empty_garbage_text_region() {
    let relative_path = "tests/fixtures/corpus/markdown/valid/empty-list-item.md.fixture";
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected empty list item fixture: {error}"));
    let document = document_for(relative_path, &source);

    assert!(document.regions.iter().any(|region| {
        region.kind == RegionKind::ListItem.as_str()
            && region.text.is_empty()
            && region.segments.is_empty()
    }));
    assert!(
        document
            .regions
            .iter()
            .filter(|region| region.kind != RegionKind::ListItem.as_str())
            .all(|region| !region.text.is_empty())
    );
}

fn document_for(relative_path: &str, source: &str) -> IrDocument {
    markdown_ir_document(source, source_identity(relative_path))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"))
}

fn degraded_region_text(document: &IrDocument) -> String {
    document
        .regions
        .iter()
        .map(|region| format!("{}: {:?}", region.kind, region.text))
        .collect::<Vec<_>>()
        .join("\n")
}
