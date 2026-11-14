//! `PyO3` regression coverage for Rust doc-comment extraction.

use pyo3::{exceptions::PyRuntimeError, prelude::Python, types::PyListMethods};

use super::{
    ExtractError,
    ExtractSyntax,
    RustExtractError,
    assert_ir_json_contract,
    bridge_extract_document,
    document_payload,
    map_extract_error,
    payload::{dict_list, dict_string, list_dict_at, parse_ir_json, region_kind_and_text},
};

/// A Rust doc-comment extraction must expose four regions and the expected
/// owner metadata.
#[rstest::rstest]
fn extract_document_py_exposes_rust_doc_comments() {
    let source =
        stilyagi_test_support::read_corpus_fixture(stilyagi_test_support::SHARED_RUST_FIXTURE_PATH)
            .expect("expected shared Rust fixture to be readable");
    let document = bridge_extract_document(&source, "rust_doc_comment")
        .expect("Rust doc-comment extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions = dict_list(document_dict, "regions").expect("Rust regions should be a list");
        let first_region = list_dict_at(&regions, 0).expect("first Rust region should be a dict");

        insta::assert_json_snapshot!(
            "extract_document_py__rust_doc_comments_payload",
            document_payload(document_dict)
        );

        assert_eq!(
            dict_string(document_dict, "syntax").expect("syntax payload should be a string"),
            ExtractSyntax::RustDocComment.as_str(),
        );
        assert_eq!(regions.len(), 4);
        assert_eq!(
            region_kind_and_text(&first_region).expect("region should carry kind and text"),
            (
                "rust_doc_comment".to_owned(),
                " Crate-level documentation comment for the shared Stilyagi corpus.".to_owned(),
            ),
        );
        let ir_json = dict_string(document_dict, "ir_json").expect("IR payload should be a string");
        let parsed_ir = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
        let first_ir_region = parsed_ir
            .get("regions")
            .and_then(serde_json::Value::as_array)
            .and_then(|region_entries| region_entries.first())
            .and_then(serde_json::Value::as_object)
            .expect("expected first IR region");
        let owner = first_ir_region
            .get("owner")
            .and_then(serde_json::Value::as_object)
            .expect("expected Rust doc-comment owner");
        assert_eq!(owner.get("kind"), Some(&serde_json::json!("module")));
        assert_eq!(owner.get("name"), Some(&serde_json::Value::Null));
        assert_eq!(owner.get("qualname"), Some(&serde_json::Value::Null));
        assert_ir_json_contract(&parsed_ir);
    });
}

/// Rust IR failures must surface as `RuntimeError` with the crate's wording.
#[rstest::rstest]
fn map_extract_error_uses_runtime_error_for_rust_ir() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::RustIr(RustExtractError::NoParseTree));

        assert!(error.is_instance_of::<PyRuntimeError>(py));
        assert!(
            error.to_string().contains("rust IR extraction failed"),
            "unexpected rust IR error display: {error}"
        );
    });
}
