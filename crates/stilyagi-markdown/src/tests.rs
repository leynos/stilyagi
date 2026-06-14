//! Unit tests for Markdown parsing and IR envelope construction.
//!
//! The fixture round-trip tests stay in this module root so their `insta`
//! snapshots remain anchored to `src/snapshots/`. Other test categories live
//! in focused sibling modules to keep each file within the size budget.

#[path = "tests/coverage.rs"]
mod coverage;
#[path = "tests/ir_consistency.rs"]
mod ir_consistency;
#[path = "tests/markers.rs"]
mod markers;
#[path = "tests/parser.rs"]
mod parser;

use std::fs;

use rstest::rstest;
use stilyagi_ir::{IrDocument, SourceIdentity, SourceSpan, SyntheticReason};
use stilyagi_test_support::{
    SHARED_MARKDOWN_FIXTURE_PATH, corpus_fixture_path, read_corpus_fixture,
};

use crate::markdown_ir_document;

/// Build a deterministic source identity for Markdown IR fixtures.
fn source_identity(path: &str) -> SourceIdentity {
    SourceIdentity::new(Some(path.to_owned()), Some(format!("file:///repo/{path}")))
}

#[rstest]
#[case(
    "tests/fixtures/corpus/markdown/valid/paragraph-inline-markup.md.fixture",
    "paragraph_inline_markup",
    "This paragraph has emphasis, strong text, inline code, and a link."
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/paragraph-soft-break.md.fixture",
    "paragraph_soft_break",
    "First line second line"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture",
    "paragraph_soft_break_crlf",
    "First CRLF line second CRLF line"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md.fixture",
    "yaml_frontmatter",
    "Paragraph after frontmatter."
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/headings.md.fixture",
    "headings",
    "Top Level"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/lists.md.fixture",
    "lists",
    "Unordered item"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/blockquotes.md.fixture",
    "blockquotes",
    "Quoted paragraph."
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/table.md.fixture",
    "table",
    "Term"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture",
    "links_and_images",
    "plain alt"
)]
#[case(
    "tests/fixtures/corpus/markdown/valid/frontmatter.md.fixture",
    "frontmatter",
    "Paragraph after dedicated frontmatter."
)]
fn hardening_fixture_ir_json_round_trips_without_span_drift(
    #[case] relative_path: &str,
    #[case] snapshot_name: &str,
    #[case] expected_paragraph: &str,
) {
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected Markdown hardening fixture: {error}"));
    let document = markdown_ir_document(&source, source_identity(relative_path))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    let json = document
        .to_canonical_json()
        .unwrap_or_else(|error| panic!("expected canonical JSON: {error}"));
    let parsed = serde_json::from_str::<IrDocument>(&json)
        .unwrap_or_else(|error| panic!("expected IR JSON round-trip: {error}"));

    assert_eq!(parsed, document);
    assert!(source_backed_segments_match_source(&parsed, &source));
    assert!(synthetic_segments_use_known_reasons(&parsed));
    assert_region_text_present(&parsed, expected_paragraph);
    insta::assert_snapshot!(snapshot_name, json);
}

#[rstest]
fn crlf_soft_break_fixture_contains_literal_crlf_bytes() {
    let path = corpus_fixture_path(
        "tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture",
    )
    .unwrap_or_else(|error| panic!("expected CRLF fixture path: {error}"));
    let bytes = fs::read(path)
        .unwrap_or_else(|error| panic!("expected readable CRLF fixture bytes: {error}"));

    assert!(bytes.windows(2).any(|pair| pair == b"\r\n"));
}

#[rstest]
fn yaml_frontmatter_fixture_records_a_yaml_node() {
    let relative_path = "tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md.fixture";
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected YAML frontmatter fixture: {error}"));
    let document = markdown_ir_document(&source, source_identity(relative_path))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));

    assert!(document.nodes.iter().any(|node| node.kind == "yaml"));
}

#[rstest]
fn shared_markdown_ir_json_round_trips_without_span_drift() {
    let source = read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected shared Markdown fixture: {error}"));
    let document = markdown_ir_document(&source, source_identity(SHARED_MARKDOWN_FIXTURE_PATH))
        .unwrap_or_else(|error| panic!("expected shared Markdown IR document: {error}"));
    let json = document
        .to_canonical_json()
        .unwrap_or_else(|error| panic!("expected canonical JSON: {error}"));
    let parsed = serde_json::from_str::<IrDocument>(&json)
        .unwrap_or_else(|error| panic!("expected IR JSON round-trip: {error}"));

    assert_eq!(parsed, document);
    assert!(
        parsed
            .regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );
    assert!(source_backed_segments_match_source(&parsed, &source));
    insta::assert_snapshot!(json);
}

fn source_backed_segments_match_source(document: &IrDocument, source: &str) -> bool {
    document.regions.iter().all(|region| {
        region.segments.iter().all(|segment| {
            segment.source.map_or_else(
                || segment.synthetic.is_some(),
                |span| source_segment_matches(span, source, &segment.text),
            )
        })
    })
}

fn source_segment_matches(span: SourceSpan, source: &str, expected: &str) -> bool {
    source.get(span.byte_start..span.byte_end) == Some(expected)
}

fn synthetic_segments_use_known_reasons(document: &IrDocument) -> bool {
    let known_reasons = SyntheticReason::ALL
        .iter()
        .map(|reason| reason.as_str())
        .collect::<Vec<_>>();
    document.regions.iter().all(|region| {
        region.segments.iter().all(|segment| {
            segment
                .synthetic
                .as_deref()
                .is_none_or(|reason| known_reasons.contains(&reason))
        })
    })
}

fn assert_region_text_present(document: &IrDocument, expected_text: &str) {
    assert!(
        document
            .regions
            .iter()
            .any(|region| region.text == expected_text)
    );
}
