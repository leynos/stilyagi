//! BDD coverage for caller-supplied source identity across the `PyO3` bridge.
//!
//! The scenario drives the registered module rather than the private
//! `extract_document_py` helper. The helper is what the module registers, so a
//! call to it proves the extraction path and says nothing about whether
//! `extract_document` was actually exposed under that name with that argument
//! shape. Building the module and calling the attribute is what a Python caller
//! does, so it is what the scenario checks.

use pyo3::{
    prelude::{Py, PyModule, Python},
    types::{PyAnyMethods, PyDict, PyTuple},
};
use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use serde_json::Value;

use crate::tests::payload::dict_item;

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
        let module = PyModule::new(py, "_stilyagi_rs_identity_bdd")
            .expect("expected a constructible bridge module");
        crate::stilyagi_rs_module(py, &module)
            .expect("expected the bridge module to register its exports");
        let extracted = module
            .getattr("extract_document")
            .expect("expected the registered extract_document export")
            .call1(args)
            .expect("expected source-aware extraction to succeed")
            .cast_into::<PyDict>()
            .expect("expected the bridge payload to be a dict");
        bridge_identity_state.extracted_document = Some(extracted.unbind());
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
        dict_item(extracted_document.bind(py), "ir_json")
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
