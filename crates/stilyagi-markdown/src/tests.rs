//! Unit tests for Markdown parsing and IR envelope construction.
//!
//! The fixture round-trip tests stay in this module root so their `insta`
//! snapshots remain anchored to `src/snapshots/`. Other test categories live
//! in focused sibling modules to keep each file within the size budget.
#![expect(
    clippy::self_named_module_files,
    reason = "tests.rs keeps the inline Markdown test harness colocated with lib.rs"
)]

macro_rules! must_ok {
    ($expression:expr, $($message:tt)+) => {
        match $expression {
            Ok(value) => value,
            Err(error) => panic!("{}: {error}", format_args!($($message)+)),
        }
    };
}

use std::path::Path;

#[derive(Debug, Clone, Copy)]
pub(super) struct ExpectedText<'a>(pub &'a str);

impl<'a> From<&'a str> for ExpectedText<'a> {
    fn from(s: &'a str) -> Self {
        Self(s)
    }
}

#[path = "tests/coverage.rs"]
mod coverage;
#[path = "tests/ir_consistency.rs"]
mod ir_consistency;
#[path = "tests/malformed.rs"]
mod malformed;
#[path = "tests/markers.rs"]
mod markers;
#[path = "tests/parser.rs"]
mod parser;
#[path = "tests/properties.rs"]
mod properties;
#[path = "tests/segment_validation.rs"]
mod segment_validation;
#[path = "tests/suppression.rs"]
mod suppression;
mod suppression_range_role;
#[path = "tests/suppression_support.rs"]
mod suppression_support;
#[path = "tests/validation_support.rs"]
mod validation_support;

use rstest::rstest;
use stilyagi_ir::{IrDocument, SourceIdentity, SourceSpan, SyntheticReason};
use stilyagi_test_support::{
    SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture, read_corpus_fixture_bytes,
};

use crate::markdown_ir_document;

/// Build a deterministic source identity for Markdown IR fixtures.
fn source_identity(path: &Path) -> SourceIdentity {
    let path_str = path.to_string_lossy();
    SourceIdentity::new(
        Some(path_str.to_string()),
        Some(format!("file:///repo/{path_str}")),
    )
}

#[rstest]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/paragraph-inline-markup.md.fixture"),
    "paragraph_inline_markup",
    ExpectedText("This paragraph has emphasis, strong text, inline code, and a link.")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/paragraph-soft-break.md.fixture"),
    "paragraph_soft_break",
    ExpectedText("First line second line")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture"),
    "paragraph_soft_break_crlf",
    ExpectedText("First CRLF line second CRLF line")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md.fixture"),
    "yaml_frontmatter",
    ExpectedText("Paragraph after frontmatter.")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/headings.md.fixture"),
    "headings",
    ExpectedText("Top Level")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/lists.md.fixture"),
    "lists",
    ExpectedText("Unordered item")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/blockquotes.md.fixture"),
    "blockquotes",
    ExpectedText("Quoted paragraph.")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/table.md.fixture"),
    "table",
    ExpectedText("Term")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture"),
    "links_and_images",
    ExpectedText("plain alt")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/frontmatter.md.fixture"),
    "frontmatter",
    ExpectedText("Paragraph after dedicated frontmatter.")
)]
#[case(
    Path::new("tests/fixtures/corpus/markdown/valid/suppression-directives.md.fixture"),
    "suppression_directives",
    ExpectedText("Apples, bananas and pears.")
)]
fn hardening_fixture_ir_json_round_trips_without_span_drift(
    #[case] relative_path: &Path,
    #[case] snapshot_name: &str,
    #[case] expected_paragraph: ExpectedText<'_>,
) {
    let relative_path_str = relative_path.to_str().expect("UTF-8 path");
    let source = must_ok!(
        read_corpus_fixture(relative_path_str),
        "expected Markdown hardening fixture"
    );
    let document = must_ok!(
        markdown_ir_document(&source, source_identity(relative_path)),
        "expected Markdown IR document"
    );
    let json = must_ok!(document.to_canonical_json(), "expected canonical JSON");
    let parsed = must_ok!(
        serde_json::from_str::<IrDocument>(&json),
        "expected IR JSON round-trip"
    );

    assert_eq!(parsed, document);
    assert!(source_backed_segments_match_source(&parsed, &source));
    assert!(synthetic_segments_use_known_reasons(&parsed));
    assert_region_text_present(&parsed, expected_paragraph);
    insta::assert_snapshot!(snapshot_name, json);
}

#[rstest]
fn crlf_soft_break_fixture_contains_literal_crlf_bytes() {
    let bytes = must_ok!(
        read_corpus_fixture_bytes(
            "tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture",
        ),
        "expected readable CRLF fixture bytes"
    );

    assert!(bytes.windows(2).any(|pair| pair == b"\r\n"));
}

#[rstest]
fn yaml_frontmatter_fixture_records_a_yaml_node() {
    let relative_path = "tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md.fixture";
    let source = must_ok!(
        read_corpus_fixture(relative_path),
        "expected YAML frontmatter fixture"
    );
    let document = must_ok!(
        markdown_ir_document(&source, source_identity(Path::new(relative_path))),
        "expected Markdown IR document"
    );

    assert!(document.nodes.iter().any(|node| node.kind == "yaml"));
}

#[rstest]
fn shared_markdown_ir_json_round_trips_without_span_drift() {
    let source = must_ok!(
        read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH),
        "expected shared Markdown fixture"
    );
    let document = must_ok!(
        markdown_ir_document(
            &source,
            source_identity(Path::new(SHARED_MARKDOWN_FIXTURE_PATH)),
        ),
        "expected shared Markdown IR document"
    );
    let json = must_ok!(document.to_canonical_json(), "expected canonical JSON");
    let parsed = must_ok!(
        serde_json::from_str::<IrDocument>(&json),
        "expected IR JSON round-trip"
    );

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

pub(super) fn source_backed_segments_match_source(document: &IrDocument, source: &str) -> bool {
    document.regions.iter().all(|region| {
        region.segments.iter().all(|segment| {
            segment.source.map_or_else(
                || segment.synthetic.is_some(),
                |span| source_segment_matches(span, source, ExpectedText(&segment.text)),
            )
        })
    })
}

fn source_segment_matches(span: SourceSpan, source: &str, expected: ExpectedText<'_>) -> bool {
    source.get(span.byte_start..span.byte_end) == Some(expected.0)
}

pub(super) fn synthetic_segments_use_known_reasons(document: &IrDocument) -> bool {
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

fn assert_region_text_present(document: &IrDocument, expected: ExpectedText<'_>) {
    assert!(
        document
            .regions
            .iter()
            .any(|region| region.text == expected.0)
    );
}

pub(super) fn regions_reconstruct_text(document: &IrDocument) -> bool {
    document
        .regions
        .iter()
        .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
}

pub(super) fn region_segments_are_contiguous(document: &IrDocument) -> bool {
    document.regions.iter().all(|region| {
        let mut expected_start = 0;
        for segment in &region.segments {
            if segment.text_start != expected_start || segment.text_end < segment.text_start {
                return false;
            }
            expected_start = segment.text_end;
        }
        expected_start == region.text.len()
    })
}

pub(super) fn parent_regions_reference_earlier_regions(document: &IrDocument) -> bool {
    let mut seen = std::collections::BTreeSet::new();
    for region in &document.regions {
        if region
            .parent_region
            .as_deref()
            .is_some_and(|parent| !seen.contains(parent))
        {
            return false;
        }
        if !seen.insert(region.id.as_str()) {
            return false;
        }
    }
    true
}
