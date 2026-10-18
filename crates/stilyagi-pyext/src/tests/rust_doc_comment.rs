//! `PyO3` regression coverage for Rust doc-comment extraction.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::Python;
use pyo3::types::{PyAnyMethods, PyDictMethods, PyList, PyListMethods};

use super::{
    ExtractError, RustExtractError, assert_ir_json_contract, bridge_extract_document,
    document_payload, map_extract_error,
};

#[rstest::rstest]
fn extract_document_py_exposes_rust_doc_comments() {
    let source =
        stilyagi_test_support::read_corpus_fixture(stilyagi_test_support::SHARED_RUST_FIXTURE_PATH)
            .expect("expected shared Rust fixture to be readable");
    let document = bridge_extract_document(&source, "rust_doc_comment")
        .expect("Rust doc-comment extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions_any = document_dict
            .get_item("regions")
            .expect("missing regions payload")
            .expect("missing regions value");
        let regions = regions_any
            .cast::<PyList>()
            .expect("Rust regions payload should be a PyList");

        insta::assert_json_snapshot!(
            "extract_document_py__rust_doc_comments_payload",
            document_payload(document_dict)
        );

        assert_eq!(regions.len(), 4);

        let ir_json = document_dict
            .get_item("ir_json")
            .expect("missing IR payload")
            .expect("missing IR value")
            .extract::<String>()
            .expect("expected IR JSON string");
        let parsed_ir: serde_json::Value =
            serde_json::from_str(&ir_json).expect("expected parseable IR JSON");
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
        assert_ir_json_contract(&ir_json);
    });
}

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
