//! Integration tests that guard extract and IR region vocabulary drift.

use rstest::rstest;
use stilyagi_extract::{ExtractSyntax, RegionKind};

use crate::test_utils::{shared_python_source, shared_rust_source};

#[test]
fn every_shared_bridge_kind_is_an_ir_kind() {
    for kind in RegionKind::ALL {
        if *kind == RegionKind::Document {
            assert_eq!(kind.ir_region_kind(), None);
            assert!(stilyagi_ir::RegionKind::try_from(kind.as_str()).is_err());
        } else {
            let expected_ir_kind = kind
                .ir_region_kind()
                .expect("non-Document kinds must map to an IR kind");
            let ir_kind = stilyagi_ir::RegionKind::try_from(kind.as_str())
                .expect("expected shared kind to have an IR spelling");
            assert_eq!(ir_kind, expected_ir_kind);
            assert_eq!(ir_kind.as_str(), kind.as_str());
        }
    }
}

#[rstest]
#[case::python_docstrings(
    ExtractSyntax::PythonDocstring,
    shared_python_source(),
    RegionKind::PythonDocstring,
    "python_docstring"
)]
#[case::rust_doc_comments(
    ExtractSyntax::RustDocComment,
    shared_rust_source(),
    RegionKind::RustDocComment,
    "rust_doc_comment"
)]
fn extracted_ir_regions_use_only_the_shared_vocabulary(
    #[case] syntax: ExtractSyntax,
    #[case] source: String,
    #[case] expected_kind: RegionKind,
    #[case] expected_spelling: &str,
) {
    let document = stilyagi_extract::extract_document(&source, syntax)
        .expect("expected shared syntax extraction");
    let ir = document.ir().expect("expected IR payload");

    assert!(!ir.regions.is_empty());
    assert_eq!(expected_kind.as_str(), expected_spelling);
    assert!(
        ir.regions
            .iter()
            .all(|region| stilyagi_ir::RegionKind::try_from(region.kind.as_str()).is_ok())
    );
    assert!(
        ir.regions
            .iter()
            .all(|region| region.kind == expected_spelling)
    );
}
