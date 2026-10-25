//! Tests for restoring canonical IR through the Python extension boundary.

use super::hydrate_ir_json_function;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Py, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyDictMethods, PyTuple};
use rstest::rstest;
use serde_json::Value;
use stilyagi_extract::{ExtractSyntax, SourceIdentity, extract_document_with_source_identity};

#[rstest]
fn hydration_round_trips_canonical_ir_and_source_identity() {
    let canonical_json = canonical_markdown_ir();
    let hydrated = bridge_hydrate_ir_json(&canonical_json);

    Python::attach(|py| {
        let payload = hydrated
            .bind(py)
            .cast::<PyDict>()
            .expect("expected hydrated document payload");
        let restored_json = payload
            .get_item("ir_json")
            .expect("expected ir_json field")
            .expect("expected canonical IR JSON")
            .extract::<String>()
            .expect("expected canonical JSON string");

        assert_eq!(restored_json, canonical_json);
    });
}

#[rstest]
#[case::malformed_known_field("/line_index", "invalid", None)]
#[case::unsupported_schema_version(
    "/schema_version",
    "99.0.0",
    Some("unsupported IR schema version '99.0.0'")
)]
#[case::unknown_syntax("/document/syntax", "unknown", Some("unknown IR syntax 'unknown'"))]
fn hydration_rejects_invalid_fields(
    #[case] pointer: &str,
    #[case] replacement: &str,
    #[case] expected_error: Option<&str>,
) {
    let mut malformed: Value = serde_json::from_str(&canonical_markdown_ir())
        .expect("expected source fixture to be valid JSON");
    let target = malformed
        .pointer_mut(pointer)
        .expect("expected canonical IR JSON pointer target");
    *target = Value::String(replacement.to_owned());
    let malformed_json = serde_json::to_string(&malformed)
        .expect("expected malformed canonical IR fixture to serialize");

    let error = assert_hydration_raises_value_error(&malformed_json);
    if let Some(expected_error_fragment) = expected_error {
        assert!(
            error.contains(expected_error_fragment),
            "expected hydration error {error:?} to contain {expected_error_fragment:?}"
        );
    }
}

fn canonical_markdown_ir() -> String {
    extract_document_with_source_identity(
        "# Heading",
        ExtractSyntax::Markdown,
        SourceIdentity::new(Some("docs/guide.md".to_owned()), None),
    )
    .expect("expected Markdown extraction")
    .ir()
    .expect("expected canonical IR")
    .to_canonical_json()
    .expect("expected canonical IR JSON")
}

fn bridge_hydrate_ir_json(canonical_json: &str) -> Py<PyDict> {
    Python::attach(|py| {
        let function =
            hydrate_ir_json_function(py).expect("expected hydration function construction");
        let arguments =
            PyTuple::new(py, [canonical_json]).expect("expected canonical JSON argument tuple");
        function
            .call(arguments, None)
            .expect("expected canonical IR hydration")
            .extract::<Py<PyDict>>()
            .expect("expected hydrated document payload")
    })
}

fn assert_hydration_raises_value_error(canonical_json: &str) -> String {
    Python::attach(|py| {
        let function =
            hydrate_ir_json_function(py).expect("expected hydration function construction");
        let arguments =
            PyTuple::new(py, [canonical_json]).expect("expected canonical JSON argument tuple");
        let Err(error) = function.call(arguments, None) else {
            panic!("expected malformed canonical IR hydration to fail");
        };
        assert!(error.is_instance_of::<PyValueError>(py));
        error.to_string()
    })
}
