//! Tests for the Python extension bridge payload and error mapping.
//!
//! The payload assertions snapshot a canonical, stable rendering of each
//! `PyDict` rather than `Bound`'s `repr()`, which can change with the
//! interpreter and with any object whose repr embeds an address. Projections
//! omit the canonical IR JSON where a structural assertion already covers it;
//! see the snapshot workflow in the developers' guide.

mod rust_doc_comment;

use super::{
    authored_directive_error_codes_py, extract_document_function, extract_document_py, hello,
    map_extract_error, supported_region_kinds_py, supported_syntaxes_py,
};
use pyo3::exceptions::{PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::{Bound, Py, PyErr, PyResult, Python};
use pyo3::types::{
    PyAny, PyAnyMethods, PyDict, PyDictMethods, PyList, PyListMethods, PyTuple, PyTupleMethods,
};
use rstest::rstest;
use serde_json::json;
use stilyagi_extract::{ExtractError, MarkdownIrFailure, PythonExtractError, RustExtractError};

/// Renders one Python tuple as a stable JSON array.
///
/// Projection functions never fail for the bridge's own payloads, so a
/// malformed payload surfaces as a test panic rather than a `Result`.
fn tuple_json(py: Python<'_>, tuple: &Py<PyTuple>) -> serde_json::Value {
    let bound = tuple.bind(py);
    let items = bound
        .iter()
        .map(|item| item.extract::<String>())
        .collect::<PyResult<Vec<_>>>()
        .expect("expected tuple items to be strings");
    json!(items)
}

/// Renders one payload value: strings stay strings, lists of region dicts
/// become JSON arrays, and anything else falls back to Python `str()`.
fn rendered_value(value: &Bound<'_, PyAny>) -> serde_json::Value {
    if let Ok(text) = value.extract::<String>() {
        return serde_json::Value::String(text);
    }

    value
        .cast::<PyList>()
        .map_or_else(|_| serde_json::Value::String(value.to_string()), list_json)
}

/// Renders one `PyDict` as a stable JSON object.
///
/// String members become JSON strings and lists of region dicts become JSON
/// arrays of objects. Any other value is rendered through Python `str()`,
/// which keeps the projection total while still making an unexpected payload
/// shape visible in the snapshot diff.
fn dictionary_json(dictionary: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = serde_json::Map::new();
    for (key, value) in dictionary.iter() {
        let rendered_key = key
            .extract::<String>()
            .expect("expected payload keys to be strings");
        rendered.insert(rendered_key, rendered_value(&value));
    }
    serde_json::Value::Object(rendered)
}

/// Renders a list of region dictionaries as a JSON array.
fn list_json(list: &Bound<'_, PyList>) -> serde_json::Value {
    let items = list
        .iter()
        .map(|item| {
            let region = item
                .cast::<PyDict>()
                .expect("expected list items to be region dicts");
            dictionary_json(region)
        })
        .collect::<Vec<_>>();
    serde_json::Value::Array(items)
}

/// Returns the bridge document payload as a stable, snapshot-friendly value.
///
/// The canonical IR JSON is dropped: it records the full document, so
/// snapshotting it here would duplicate an existing golden-IR snapshot and
/// bury the bridge shape in hundreds of lines of IR.
pub(super) fn document_payload(payload: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = document_payload_with_ir(payload);
    if let serde_json::Value::Object(ref mut map) = rendered {
        map.remove("ir_json");
    }
    rendered
}

/// Returns the whole bridge payload, canonical IR JSON included.
pub(super) fn document_payload_with_ir(payload: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = dictionary_json(payload);
    let Some(map) = rendered.as_object_mut() else {
        return rendered;
    };
    let Some(serde_json::Value::String(ir_json)) = map.get("ir_json").cloned() else {
        return rendered;
    };
    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&ir_json) {
        map.insert("ir_json".to_owned(), parsed);
    }
    rendered
}

fn bridge_extract_document(source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
    Python::attach(|py| {
        let args = PyTuple::new(py, [source, syntax])?;
        extract_document_py(py, &args)
    })
}

fn invalid_syntax_error(syntax: &str) -> PyErr {
    bridge_extract_document("Example", syntax)
        .expect_err(&format!("expected an error for syntax {syntax:?}"))
}

fn assert_ir_json_contract(ir_json: &str) {
    let parsed = match serde_json::from_str::<serde_json::Value>(ir_json) {
        Ok(parsed) => parsed,
        Err(error) => panic!("expected parseable IR JSON: {error}"),
    };

    assert_eq!(
        parsed.get("schema_version"),
        Some(&serde_json::json!("1.1.0"))
    );
    assert!(
        parsed
            .get("document")
            .is_some_and(serde_json::Value::is_object)
    );

    let Some(line_index) = parsed
        .get("line_index")
        .and_then(serde_json::Value::as_array)
    else {
        panic!("expected line_index array");
    };
    assert_eq!(line_index.first(), Some(&serde_json::json!(0)));

    assert!(
        parsed
            .get("regions")
            .is_some_and(serde_json::Value::is_array)
    );
}

fn assert_supported_tuple_snapshot(
    py: Python<'_>,
    tuple_result: PyResult<Py<PyTuple>>,
    snapshot_name: &str,
    failure_context: &str,
) {
    let supported_values = match tuple_result {
        Ok(tuple) => tuple,
        Err(error) => panic!("unexpected {failure_context} failure: {error}"),
    };

    insta::assert_json_snapshot!(snapshot_name, tuple_json(py, &supported_values));
}

#[rstest]
fn hello_delegates_to_the_core_smoke_greeting() {
    assert_eq!(hello(), stilyagi_core::smoke_hello());
}

#[rstest]
#[case("hello from Python")]
fn hello_is_not_the_legacy_python_fallback(#[case] legacy_fallback: &str) {
    assert_ne!(hello(), legacy_fallback);
}

#[rstest]
fn supported_syntaxes_follow_the_rust_extraction_vocabulary() {
    Python::attach(|py| {
        assert_supported_tuple_snapshot(
            py,
            supported_syntaxes_py(py),
            "supported_syntaxes",
            "supported_syntaxes",
        );
    });
}

#[rstest]
fn supported_region_kinds_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        assert_supported_tuple_snapshot(
            py,
            supported_region_kinds_py(py),
            "supported_region_kinds",
            "supported_region_kinds",
        );
    });
}

#[rstest]
fn authored_directive_error_codes_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        assert_supported_tuple_snapshot(
            py,
            authored_directive_error_codes_py(py),
            "authored_directive_error_codes",
            "authored_directive_error_codes",
        );
    });
}

#[rstest]
fn extract_document_function_rejects_unexpected_kwargs() {
    Python::attach(|py| {
        let function =
            extract_document_function(py).expect("expected extract_document function construction");
        let args = PyTuple::new(py, ["# Heading", "markdown"]).expect("expected argument tuple");
        let kwargs = PyDict::new(py);
        kwargs
            .set_item("unexpected", true)
            .expect("expected kwargs setup to succeed");
        let error = function
            .call(args, Some(&kwargs))
            .expect_err("expected unexpected keyword argument to fail");

        assert!(error.is_instance_of::<PyTypeError>(py));
    });
}

#[rstest]
fn extract_document_py_exposes_markdown_document() {
    Python::attach(|py| {
        let args = PyTuple::new(py, ["# Heading", "markdown"]).expect("expected argument tuple");
        let document_result = extract_document_py(py, &args);

        assert!(document_result.is_ok());
        let extracted_document = match document_result {
            Ok(document) => document,
            Err(error) => panic!("unexpected extraction failure: {error}"),
        };
        let extracted_document_bound = extracted_document.bind(py);
        let extracted_document_dict = extracted_document_bound
            .cast::<PyDict>()
            .expect("extracted Markdown document should be a PyDict");

        insta::assert_json_snapshot!(
            "extract_document_py__markdown_payload",
            document_payload(extracted_document_dict)
        );

        let ir_json = extracted_document_dict
            .get_item("ir_json")
            .expect("expected IR payload lookup to succeed")
            .expect("missing IR payload")
            .extract::<String>()
            .expect("expected IR JSON string");
        assert_ir_json_contract(&ir_json);
    });
}

#[rstest]
fn extract_document_py_exposes_python_docstrings() {
    let source = "\"\"\"Module docs.\"\"\"\n\ndef example():\n    \"\"\"Function docs.\"\"\"\n";
    let document = bridge_extract_document(source, "python_docstring")
        .expect("Python docstring extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions_any = document_dict
            .get_item("regions")
            .expect("missing regions payload")
            .expect("missing regions value");
        let regions = regions_any
            .cast::<PyList>()
            .expect("Python regions payload should be a PyList");

        insta::assert_json_snapshot!(
            "extract_document_py__python_docstring_payload",
            document_payload(document_dict)
        );

        assert_eq!(regions.len(), 2);

        let ir_json = document_dict
            .get_item("ir_json")
            .expect("missing IR payload")
            .expect("missing IR value")
            .extract::<String>()
            .expect("expected IR JSON string");
        assert_ir_json_contract(&ir_json);
    });
}

/// Keep rejection behaviour stable for both unsupported and unknown syntax
/// strings.
#[rstest]
#[case("not_a_syntax", "extract_document_py__invalid_syntax_error")]
fn extract_document_py_rejects_invalid_syntaxes(#[case] syntax: &str, #[case] snapshot_name: &str) {
    let err = invalid_syntax_error(syntax);
    insta::assert_snapshot!(snapshot_name, format!("{err}"));
}

/// Keep the `UnknownSyntax` arm of `map_extract_error` wired to a
/// `PyValueError` so Python callers receive a `ValueError` for unrecognised
/// syntax strings.
#[rstest]
fn bridge_extract_document_rejects_unknown_syntaxes() {
    let error_result = bridge_extract_document("example", "not_a_real_syntax");

    assert!(error_result.is_err());
    let error = match error_result {
        Ok(document) => panic!("expected unknown syntax error, got {document:?}"),
        Err(error) => error,
    };
    Python::attach(|py| {
        assert!(error.is_instance_of::<PyValueError>(py));
    });
    assert!(error.to_string().contains("not_a_real_syntax"));
}

#[rstest]
fn map_extract_error_uses_runtime_error_for_markdown_ir() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::MarkdownIr(MarkdownIrFailure::new(
            "stilyagi-markdown",
            "bad-ir",
            "bad IR",
        )));

        assert!(error.is_instance_of::<PyRuntimeError>(py));
    });
}

#[rstest]
fn map_extract_error_uses_runtime_error_for_python_ir() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::PythonIr(PythonExtractError::NoParseTree));

        assert!(error.is_instance_of::<PyRuntimeError>(py));
        assert!(
            error.to_string().contains("python IR extraction failed"),
            "unexpected python IR error display: {error}"
        );
    });
}

#[rstest]
fn map_extract_error_uses_value_error_for_unknown_syntax() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::UnknownSyntax("bogus".to_owned()));

        assert!(error.is_instance_of::<PyValueError>(py));
    });
}
