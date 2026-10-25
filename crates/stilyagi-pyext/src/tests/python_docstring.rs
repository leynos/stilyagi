//! Python docstring extraction contracts across the `PyO3` bridge.

use pyo3::prelude::Python;
use pyo3::types::{PyAnyMethods, PyDict, PyList};
use rstest::rstest;
use stilyagi_extract::ExtractSyntax;

use super::{BridgeExtractRequest, assert_ir_json_contract, bridge_extract_document, region_at};

/// State the stable fields expected from one extracted region.
#[derive(Clone, Copy)]
struct RegionExpectation<'a> {
    kind: &'a str,
    text: &'a str,
}

fn assert_region(region: &pyo3::Bound<'_, PyDict>, expected: RegionExpectation<'_>) {
    for (key, expected_value) in [("kind", expected.kind), ("text", expected.text)] {
        let value = match region.get_item(key) {
            Ok(payload) => payload,
            Err(error) => panic!("missing {key} payload: {error}"),
        };
        let actual = match value.extract::<String>() {
            Ok(text) => text,
            Err(error) => panic!("expected {key} string: {error}"),
        };
        assert_eq!(actual, expected_value, "unexpected {key}");
    }
}

#[rstest]
fn extract_document_py_exposes_python_docstrings() {
    let source = "\"\"\"Module docs.\"\"\"\n\ndef example():\n    \"\"\"Function docs.\"\"\"\n";
    let document = bridge_extract_document(&BridgeExtractRequest {
        source,
        syntax: "python_docstring",
        source_path: None,
    })
    .expect("Python docstring extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions_any = document_dict
            .get_item("regions")
            .expect("missing regions payload");
        let regions = regions_any
            .cast::<PyList>()
            .expect("Python regions payload should be a PyList");

        assert_eq!(
            document_dict
                .get_item("syntax")
                .expect("missing syntax payload")
                .extract::<&str>()
                .expect("expected syntax string"),
            ExtractSyntax::PythonDocstring.as_str(),
        );
        assert_eq!(regions.len().expect("expected list length"), 2);
        assert_region(
            &region_at(regions, 0),
            RegionExpectation {
                kind: "python_docstring",
                text: "Module docs.",
            },
        );
        assert_region(
            &region_at(regions, 1),
            RegionExpectation {
                kind: "python_docstring",
                text: "Function docs.",
            },
        );

        let ir_json = document_dict
            .get_item("ir_json")
            .expect("missing IR payload")
            .extract::<String>()
            .expect("expected IR JSON string");
        assert_ir_json_contract(&ir_json);
    });
}
