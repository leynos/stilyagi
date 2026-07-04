//! `PyO3` regression coverage for Rust doc-comment extraction.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::Python;
use pyo3::types::{PyAnyMethods, PyDictMethods, PyList, PyListMethods};

use super::{
    ExtractError, ExtractSyntax, RustExtractError, assert_ir_json_contract,
    bridge_extract_document, map_extract_error, region_at,
};

#[rstest::rstest]
fn extract_document_py_exposes_rust_doc_comments() {
    let source =
        stilyagi_test_support::read_corpus_fixture(stilyagi_test_support::SHARED_RUST_FIXTURE_PATH)
            .expect("expected shared Rust fixture to be readable");
    let document = bridge_extract_document(&source, "rust_doc_comment")
        .unwrap_or_else(|error| panic!("unexpected extraction failure: {error}"));

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions_any = document_dict
            .get_item("regions")
            .expect("missing regions payload");
        let regions_value = regions_any.expect("missing regions value");
        let regions = regions_value
            .cast::<PyList>()
            .unwrap_or_else(|error| panic!("expected PyList but got {error}"));
        let first_region = region_at(regions, 0);

        assert_eq!(
            document_dict
                .get_item("syntax")
                .expect("missing syntax payload")
                .expect("missing syntax value")
                .extract::<&str>()
                .expect("expected syntax string"),
            ExtractSyntax::RustDocComment.as_str(),
        );
        assert_eq!(regions.len(), 4);
        assert_eq!(
            first_region
                .get_item("kind")
                .expect("missing kind payload")
                .expect("missing kind value")
                .extract::<&str>()
                .expect("expected kind string"),
            "rust_doc_comment",
        );
        assert_eq!(
            first_region
                .get_item("text")
                .expect("missing text payload")
                .expect("missing text value")
                .extract::<&str>()
                .expect("expected text string"),
            " Crate-level documentation comment for the shared Stilyagi corpus.",
        );
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
