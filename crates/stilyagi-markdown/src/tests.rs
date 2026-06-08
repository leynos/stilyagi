//! Unit tests for Markdown parsing and IR envelope construction.

use std::{collections::BTreeSet, fs};

use markdown::mdast::Node;
use rstest::rstest;
use stilyagi_ir::{IrDocument, SourceIdentity, SourceSpan};
use stilyagi_test_support::{
    SHARED_MARKDOWN_FIXTURE_PATH, corpus_fixture_path, read_corpus_fixture,
};

use super::{
    MarkdownBoundary, MarkdownDiagnosticContext, markdown_ir_document, parse_markdown_ast,
    parse_markdown_ast_with, validate_ir_consistency,
};

/// Keep the marker type default stable and comparable.
#[test]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises the Default implementation"
)]
fn markdown_boundary_default_matches_the_marker_value() {
    assert_eq!(MarkdownBoundary::default(), MarkdownBoundary);
}

/// Keep the marker type clone semantics trivial.
#[test]
fn markdown_boundary_clone_matches_the_original() {
    let boundary = MarkdownBoundary;

    assert_eq!(boundary.clone(), boundary);
}

/// Keep the marker type debug output identifiable in failures.
#[test]
fn markdown_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{MarkdownBoundary:?}").contains("MarkdownBoundary"));
}

/// Keep the marker type copy semantics available to callers.
#[test]
fn markdown_boundary_is_copy() {
    let original = MarkdownBoundary;
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first, original);
}

#[rstest]
fn markdown_parser_reports_positions_for_representative_blocks() {
    let source = "# Heading\n\nA paragraph with [a link](https://example.com).\n";
    let tree = parse_markdown_ast(source);

    assert!(matches!(&tree, Ok(Node::Root(_))));
    if let Ok(root) = tree {
        assert_node_start(&root, 0);
        assert_node_has_non_empty_span(&root);
        assert!(find_kind(&root, NodeKind::Heading).is_some());
        assert!(find_kind(&root, NodeKind::Paragraph).is_some());
        if let Some(heading) = find_kind(&root, NodeKind::Heading) {
            assert_node_start(heading, 0);
            assert_node_has_non_empty_span(heading);
        }
        if let Some(paragraph) = find_kind(&root, NodeKind::Paragraph) {
            assert_node_start(paragraph, 11);
            assert_node_has_non_empty_span(paragraph);
        }
    }
}

#[rstest]
fn markdown_parser_panics_are_contained_as_messages() {
    let result = parse_markdown_ast_with("content", |_| panic!("forced parser panic"));

    assert!(matches!(
        result,
        Err(ref error)
            if error.reason.contains("forced parser panic")
                && error.reason.contains("phase=parse")
                && error.reason.contains("path=<unknown>")
                && error.reason.contains("uri=<unknown>")
                && error.rule_id.as_ref() == "parser-panic"
                && error.source.as_ref() == "stilyagi-markdown"
    ));
}

#[derive(Clone, Copy)]
enum NodeKind {
    Heading,
    Paragraph,
}

fn find_kind(node: &Node, kind: NodeKind) -> Option<&Node> {
    if matches_kind(node, kind) {
        return Some(node);
    }
    if let Some(children) = node.children() {
        for child in children {
            if let Some(found) = find_kind(child, kind) {
                return Some(found);
            }
        }
    }
    None
}

fn matches_kind(node: &Node, kind: NodeKind) -> bool {
    matches!(
        (node, kind),
        (Node::Heading(_), NodeKind::Heading) | (Node::Paragraph(_), NodeKind::Paragraph)
    )
}

fn assert_node_start(node: &Node, start: usize) {
    let position = node.position();
    assert!(matches!(
        position,
        Some(value) if value.start.offset == start
    ));
}

fn assert_node_has_non_empty_span(node: &Node) {
    let position = node.position();
    assert!(matches!(
        position,
        Some(value) if value.start.offset < value.end.offset
    ));
}

const fn diagnostic_context() -> MarkdownDiagnosticContext<'static> {
    MarkdownDiagnosticContext {
        phase: "validate",
        path: "docs/example.md",
        uri: "file:///repo/docs/example.md",
    }
}

#[rstest]
fn markdown_ir_document_emits_envelope_nodes_and_regions() {
    let source = "# Fixture Heading\n\nThis paragraph links to the\n[Stilyagi design](../../../../../docs/stilyagi-design.md).\n\n| Term | Meaning |\n| ---- | ------- |\n| IR   | Intermediate representation |\n";
    let document = markdown_ir_document(
        source,
        source_identity("tests/fixtures/corpus/markdown/valid/example.md"),
    );

    assert!(matches!(&document, Ok(value) if value.document.syntax == "markdown"));
    if let Ok(value) = document {
        assert_eq!(value.schema_version, "1.0.0");
        assert!(
            value
                .producers
                .iter()
                .any(|producer| { producer.kind == "markdown" && producer.name == "markdown-rs" })
        );
        assert!(value.document.content_hash.starts_with("sha256:"));
        assert_eq!(value.line_index.first().copied(), Some(0));
        assert!(!value.nodes.is_empty());
        assert!(
            value
                .regions
                .iter()
                .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
        );
        assert!(region_kinds(&value.regions).contains("heading"));
        assert!(region_kinds(&value.regions).contains("paragraph"));
        assert!(region_kinds(&value.regions).contains("table_cell"));
    }
}

#[rstest]
fn markdown_ir_document_preserves_canonical_source_identity_helpers() {
    let source = "# Heading\n\nBody";
    let document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));

    assert_eq!(
        document.document.content_hash,
        stilyagi_ir::content_hash_for(source)
    );
    assert_eq!(document.line_index, stilyagi_ir::line_index_for(source));
}

#[rstest]
fn validate_ir_consistency_reports_content_hash_mismatches() {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    document.document.content_hash = "sha256:bad".to_owned();
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    assert!(matches!(
        result,
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "ir-content-hash-mismatch"
                && error.reason.contains("phase=validate")
                && error.reason.contains("path=")
                && error.reason.contains("uri=")
                && error.reason.contains("content_hash mismatch")
    ));
}

#[rstest]
fn validate_ir_consistency_reports_line_index_mismatches() {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    document.line_index.push(usize::MAX);
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    assert!(matches!(
        result,
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "ir-line-index-mismatch"
                && error.reason.contains("phase=validate")
                && error.reason.contains("line_index mismatch")
    ));
}

#[rstest]
fn markdown_ir_document_records_soft_breaks_as_synthetic_segments() {
    let source = "First line\nsecond line\n";
    let document = markdown_ir_document(source, source_identity("docs/example.md"));

    assert!(matches!(&document, Ok(value) if value.regions.len() == 1));
    if let Ok(value) = document {
        let paragraph = value.regions.first();
        assert_eq!(
            paragraph.map(|region| region.text.as_str()),
            Some("First line second line")
        );
        assert!(matches!(
            paragraph,
            Some(region) if region.segments.iter().any(|segment| segment.synthetic.as_deref() == Some("softbreak_space"))
        ));
    }
}

#[rstest]
fn markdown_ir_document_keeps_empty_heading_regions() {
    let document = markdown_ir_document("#\n", source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));

    assert!(document.regions.iter().any(|region| {
        region.kind == "heading"
            && region.text.is_empty()
            && region.segments.is_empty()
            && region.natural_language.is_none()
    }));
}

#[rstest]
fn markdown_ir_document_uses_synthetic_segment_for_decoded_text() {
    let document = markdown_ir_document("AT&amp;T", source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    let paragraph = document
        .regions
        .iter()
        .find(|region| region.kind == "paragraph")
        .unwrap_or_else(|| panic!("expected paragraph region"));

    assert_eq!(paragraph.text, "AT&T");
    assert!(paragraph.segments.iter().all(|segment| {
        segment.source.is_none() && segment.synthetic.as_deref() == Some("decoded_text")
    }));
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

fn region_kinds(regions: &[stilyagi_ir::IrRegion]) -> BTreeSet<&str> {
    regions.iter().map(|region| region.kind.as_str()).collect()
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

fn source_identity(path: &str) -> SourceIdentity {
    SourceIdentity::new(Some(path.to_owned()), Some(format!("file:///repo/{path}")))
}

fn source_segment_matches(span: SourceSpan, source: &str, expected: &str) -> bool {
    source.get(span.byte_start..span.byte_end) == Some(expected)
}

fn synthetic_segments_use_known_reasons(document: &IrDocument) -> bool {
    document.regions.iter().all(|region| {
        region.segments.iter().all(|segment| {
            segment.synthetic.as_deref().is_none_or(|reason| {
                matches!(
                    reason,
                    "softbreak_space" | "hardbreak_space" | "decoded_text"
                )
            })
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
