//! Unit tests for IR domain invariants and canonical document helpers.

use std::collections::BTreeMap;

use proptest::prelude::*;
use rstest::rstest;

use super::{
    DocumentMetadata, IrBoundary, IrDocument, IrRegion, IrSegment, SegmentOrigin, SourceSpan,
    content_hash_for,
};

/// Keep the marker type default stable and comparable.
#[test]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises the Default implementation"
)]
fn ir_boundary_default_matches_the_marker_value() {
    assert_eq!(IrBoundary::default(), IrBoundary);
}

/// Keep the marker type clone semantics trivial.
#[test]
fn ir_boundary_clone_matches_the_original() {
    let boundary = IrBoundary;

    assert_eq!(boundary.clone(), boundary);
}

/// Keep the marker type debug output identifiable in failures.
#[test]
fn ir_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{IrBoundary:?}").contains("IrBoundary"));
}

/// Keep the marker type copy semantics available to callers.
#[test]
fn ir_boundary_is_copy() {
    let original = IrBoundary;
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first, original);
}

#[rstest]
fn empty_document_uses_line_index_and_content_hash() {
    let source = "# Title\nBody";
    let document = IrDocument::empty(
        DocumentMetadata::markdown("docs/example.md", "file:///repo/docs/example.md", source),
        Vec::new(),
        source,
    );

    assert_eq!(document.schema_version, "1.0.0");
    assert_eq!(document.line_index, vec![0, 8, 12]);
    assert!(document.document.content_hash.starts_with("sha256:"));
}

#[rstest]
fn empty_document_derives_content_hash_from_source() {
    let document = IrDocument::empty(
        DocumentMetadata {
            uri: "file:///repo/docs/example.md".to_owned(),
            path: "docs/example.md".to_owned(),
            syntax: "markdown".to_owned(),
            natural_language: None,
            encoding: "utf-8".to_owned(),
            content_hash: "sha256:not-the-source".to_owned(),
        },
        Vec::new(),
        "# Title\nBody",
    );

    assert_eq!(
        document.document.content_hash,
        content_hash_for("# Title\nBody"),
    );
}

#[rstest]
fn canonical_json_orders_metadata_deterministically() {
    let mut metadata = BTreeMap::new();
    metadata.insert("zeta".to_owned(), serde_json::json!(true));
    metadata.insert("alpha".to_owned(), serde_json::json!(1));
    let mut document = IrDocument::empty(
        DocumentMetadata::markdown("docs/example.md", "file:///repo/docs/example.md", ""),
        Vec::new(),
        "",
    );
    document.metadata = metadata;

    let json = document.to_canonical_json();

    assert!(matches!(
        json,
        Ok(ref value) if value.contains("\"alpha\"") && value.contains("\"zeta\"")
    ));
    if let Ok(value) = json {
        let alpha_position = value.find("\"alpha\"");
        let zeta_position = value.find("\"zeta\"");
        assert!(matches!(
            (alpha_position, zeta_position),
            (Some(alpha), Some(zeta)) if alpha < zeta
        ));
    }
}

#[derive(Debug, Clone)]
enum SegmentSpec {
    Source(String),
    Synthetic(&'static str),
}

fn segment_spec() -> impl Strategy<Value = SegmentSpec> {
    prop_oneof![
        "[a-z]{1,8}".prop_map(SegmentSpec::Source),
        prop_oneof![Just("softbreak_space"), Just("hardbreak_space")]
            .prop_map(SegmentSpec::Synthetic),
    ]
}

proptest! {
    #[test]
    fn generated_segments_preserve_layout_and_source_invariants(
        specs in prop::collection::vec(segment_spec(), 1..12),
    ) {
        let (region, source) = region_from_specs(&specs);

        prop_assert!(region.segments_reconstruct_text());
        prop_assert!(segments_are_contiguous(&region));
        prop_assert!(source_backed_segments_match_source(&region, &source));
        prop_assert!(synthetic_segments_use_known_reasons(&region));
    }
}

fn region_from_specs(specs: &[SegmentSpec]) -> (IrRegion, String) {
    let mut source = String::new();
    let mut region_text = String::new();
    let mut segments = Vec::new();
    for spec in specs {
        match spec {
            SegmentSpec::Source(text) => {
                let text_start = region_text.len();
                let source_start = source.len();
                source.push_str(text);
                region_text.push_str(text);
                segments.push(IrSegment::new(
                    text_start,
                    text.clone(),
                    SegmentOrigin::Source {
                        span: SourceSpan::new(source_start, source.len()),
                        node: "n1".to_owned(),
                    },
                ));
            }
            SegmentSpec::Synthetic(reason) => {
                let text_start = region_text.len();
                region_text.push(' ');
                segments.push(IrSegment::new(
                    text_start,
                    " ",
                    SegmentOrigin::Synthetic {
                        reason: (*reason).to_owned(),
                    },
                ));
            }
        }
    }
    (
        IrRegion {
            id: "r1".to_owned(),
            kind: "paragraph".to_owned(),
            scope: vec!["markdown".to_owned(), "paragraph".to_owned()],
            syntax: "markdown".to_owned(),
            natural_language: Some("en".to_owned()),
            text: region_text,
            segments,
            origin_nodes: vec!["n1".to_owned()],
            owner: None,
            attrs: BTreeMap::new(),
            parent_region: None,
        },
        source,
    )
}

fn segments_are_contiguous(region: &IrRegion) -> bool {
    let mut expected_start = 0;
    for segment in &region.segments {
        if segment.text_start != expected_start || segment.text_end < segment.text_start {
            return false;
        }
        expected_start = segment.text_end;
    }
    expected_start == region.text.len()
}

fn source_backed_segments_match_source(region: &IrRegion, source: &str) -> bool {
    region.segments.iter().all(|segment| {
        segment.source.map_or_else(
            || segment.synthetic.is_some() && segment.node.is_none(),
            |span| {
                segment.synthetic.is_none()
                    && segment.node.as_deref() == Some("n1")
                    && source.get(span.byte_start..span.byte_end) == Some(segment.text.as_str())
            },
        )
    })
}

fn synthetic_segments_use_known_reasons(region: &IrRegion) -> bool {
    region.segments.iter().all(|segment| {
        segment
            .synthetic
            .as_deref()
            .is_none_or(|reason| matches!(reason, "softbreak_space" | "hardbreak_space"))
    })
}
