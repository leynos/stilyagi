//! BDD coverage for caller-supplied source identity across the `PyO3` bridge.

use pyo3::prelude::{Py, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyTuple};
use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use serde_json::Value;

struct BridgeIdentityState {
    extracted_document: Option<Py<PyDict>>,
}

#[fixture]
fn bridge_identity_state() -> BridgeIdentityState {
    BridgeIdentityState {
        extracted_document: None,
    }
}

#[given("the bridge identity fixture is ready")]
fn bridge_identity_fixture_is_ready() {}

#[when("the bridge extracts Markdown with a reported source path")]
fn bridge_extracts_markdown_with_a_reported_source_path(
    bridge_identity_state: &mut BridgeIdentityState,
) {
    Python::attach(|py| {
        let args = PyTuple::new(py, ["# Heading", "markdown", "docs/guide.mdc"])
            .expect("expected bridge argument tuple");
        bridge_identity_state.extracted_document = Some(
            crate::extract_document_py(py, &args)
                .expect("expected source-aware extraction to succeed"),
        );
    });
}

#[then("canonical IR retains the reported path and has no URI")]
fn canonical_ir_retains_the_reported_path_and_has_no_uri(
    bridge_identity_state: &BridgeIdentityState,
) {
    let extracted_document = bridge_identity_state
        .extracted_document
        .as_ref()
        .expect("expected an extracted bridge document");
    let ir_json = Python::attach(|py| {
        extracted_document
            .bind(py)
            .get_item("ir_json")
            .expect("expected canonical IR")
            .extract::<String>()
            .expect("expected canonical IR JSON string")
    });
    let ir: Value = serde_json::from_str(&ir_json).expect("expected valid canonical IR");

    let document = ir
        .get("document")
        .expect("expected document metadata in canonical IR");
    assert_eq!(
        document.get("path").and_then(Value::as_str),
        Some("docs/guide.mdc")
    );
    assert!(document.get("uri").is_some_and(Value::is_null));
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge reports the caller-supplied Markdown path in canonical IR"
)]
fn bridge_reports_the_caller_supplied_markdown_path(
    #[from(bridge_identity_state)] _bridge_identity_state: BridgeIdentityState,
) {
}
