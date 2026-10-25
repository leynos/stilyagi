//! Source identity contracts across the `PyO3` extraction boundary.

use super::{BridgeExtractRequest, bridge_extract_document, extract_document_py};
use pyo3::prelude::Python;
use pyo3::types::{PyAnyMethods, PyDict, PyDictMethods, PyTuple};
use rstest::rstest;
use serde_json::Value;

#[rstest]
#[case("docs/guide.md")]
#[case("nested/frontmatter.mdc")]
fn bridge_preserves_reported_path_and_leaves_uri_absent(#[case] path: &str) {
    let payload = bridge_extract_document(&BridgeExtractRequest {
        source: "# Heading",
        syntax: "markdown",
        source_path: Some(path),
    })
    .expect("expected the bridge to extract Markdown with an identity");
    let ir_json = canonical_ir_json(&payload);
    let ir: Value = serde_json::from_str(&ir_json).expect("expected valid canonical IR");

    let document = document_metadata(&ir);
    assert_eq!(document.get("path").and_then(Value::as_str), Some(path));
    assert!(document.get("uri").is_some_and(Value::is_null));
}

#[rstest]
fn bridge_keeps_two_argument_calls_anonymous() {
    let payload = bridge_extract_document(&BridgeExtractRequest {
        source: "# Heading",
        syntax: "markdown",
        source_path: None,
    })
    .expect("expected the legacy bridge call shape to keep working");
    let ir_json = canonical_ir_json(&payload);
    let ir: Value = serde_json::from_str(&ir_json).expect("expected valid canonical IR");

    let document = document_metadata(&ir);
    assert!(document.get("path").is_some_and(Value::is_null));
    assert!(document.get("uri").is_some_and(Value::is_null));
}

#[rstest]
fn bridge_accepts_explicit_none_as_anonymous_identity() {
    let payload = Python::attach(|py| {
        let args = PyTuple::new(py, [Some("# Heading"), Some("markdown"), None::<&str>])?;
        extract_document_py(py, &args)
    })
    .expect("expected an explicit None source path to preserve anonymous identity");
    let ir_json = canonical_ir_json(&payload);
    let ir: Value = serde_json::from_str(&ir_json).expect("expected valid canonical IR");

    let document = document_metadata(&ir);
    assert!(document.get("path").is_some_and(Value::is_null));
    assert!(document.get("uri").is_some_and(Value::is_null));
}

fn document_metadata(ir: &Value) -> &Value {
    ir.get("document")
        .expect("expected document metadata in canonical IR")
}

fn canonical_ir_json(payload: &pyo3::Py<PyDict>) -> String {
    Python::attach(|py| {
        payload
            .bind(py)
            .get_item("ir_json")
            .expect("expected ir_json field")
            .expect("expected canonical IR JSON")
            .extract::<String>()
            .expect("expected canonical IR as a string")
    })
}
