//! Property tests for generated IR segment layout invariants.

use std::collections::BTreeMap;

use proptest::prelude::*;
use rstest::rstest;

use crate::{IrRegion, IrSegment, SegmentOrigin, SourceSpan, SyntheticReason};

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

#[rstest]
fn segments_reconstruct_text_rejects_gapped_ranges() {
    let (mut region, _source) = region_from_specs(&[SegmentSpec::Source("alpha".to_owned())]);
    let segment = region
        .segments
        .first_mut()
        .expect("expected generated region to contain a segment");
    segment.text_start = 1;
    segment.text_end = 6;

    assert!(!region.segments_reconstruct_text());
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
                        span: SourceSpan::new(source_start, source.len()).expect(
                            "expected source span to be valid for region fixture construction",
                        ),
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
            natural_language: None,
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
    let known_reasons = SyntheticReason::ALL
        .iter()
        .map(|reason| reason.as_str())
        .collect::<Vec<_>>();
    region.segments.iter().all(|segment| {
        segment
            .synthetic
            .as_deref()
            .is_none_or(|reason| known_reasons.contains(&reason))
    })
}
