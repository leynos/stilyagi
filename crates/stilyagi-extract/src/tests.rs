//! Crate-private tests for extraction error mapping and region vocabulary.

use super::{
    ExtractError, ExtractSyntax, MarkdownIrFailure, PythonExtractError, RegionKind,
    RustExtractError, extract_markdown_document_with,
};
use rstest::rstest;
use std::error::Error as _;

const KNOWN_REGION_KINDS: &[RegionKind] = &[
    RegionKind::Document,
    RegionKind::PythonDocstring,
    RegionKind::RustDocComment,
];

const fn known_region_kind(kind: RegionKind) {
    match kind {
        RegionKind::Document | RegionKind::PythonDocstring | RegionKind::RustDocComment => {}
    }
}

#[test]
fn region_kind_all_is_exhaustive() {
    for kind in KNOWN_REGION_KINDS {
        known_region_kind(*kind);
    }

    assert_eq!(RegionKind::ALL, KNOWN_REGION_KINDS);
}

#[test]
fn region_kind_spellings_round_trip_through_the_bridge_parser() {
    for kind in RegionKind::ALL {
        assert_eq!(RegionKind::try_from(kind.as_str()), Ok(*kind));
    }
}

#[test]
fn shared_bridge_spelling_comes_from_ir() {
    assert_eq!(RegionKind::Document.ir_region_kind(), None);
    assert!(stilyagi_ir::RegionKind::try_from(RegionKind::Document.as_str()).is_err());

    for kind in RegionKind::ALL {
        if *kind == RegionKind::Document {
            continue;
        }

        let ir_kind = kind
            .ir_region_kind()
            .expect("non-Document kinds must map to an IR kind");
        assert_eq!(kind.as_str(), ir_kind.as_str());
    }
}

#[rstest]
fn markdown_ir_builder_failures_map_to_extract_error() {
    let result = extract_markdown_document_with("# Heading", |_| {
        Err(MarkdownIrFailure::new(
            "stilyagi-markdown",
            "injected-ir-failure",
            "injected IR failure",
        ))
    });
    let Err(ExtractError::MarkdownIr(diagnostic)) = result else {
        panic!("expected MarkdownIr failure");
    };
    assert_eq!(diagnostic.source, "stilyagi-markdown");
    assert_eq!(diagnostic.rule_id, "injected-ir-failure");
    assert_eq!(diagnostic.reason, "injected IR failure");
}

#[rstest]
#[case::python(
    ExtractError::PythonIr(PythonExtractError::GrammarLoad),
    Some(PythonExtractError::GrammarLoad.to_string()),
)]
#[case::rust(
    ExtractError::RustIr(RustExtractError::NoParseTree),
    Some(RustExtractError::NoParseTree.to_string()),
)]
#[case::unsupported_syntax(ExtractError::UnsupportedSyntax(ExtractSyntax::Markdown), None)]
#[case::unknown_syntax(ExtractError::UnknownSyntax("unknown".to_owned()), None)]
#[case::markdown_ir(
    ExtractError::MarkdownIr(MarkdownIrFailure::new("source", "rule", "reason")),
    None
)]
fn extract_error_source_matches_variant(
    #[case] error: ExtractError,
    #[case] expected_source: Option<String>,
) {
    assert_eq!(error.source().map(ToString::to_string), expected_source);
}
