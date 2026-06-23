//! Tests for the Python extension bridge payload and error mapping.

use super::{
    extract_document_function, extract_document_py, hello, map_extract_error,
    supported_region_kinds_py, supported_syntaxes_py,
};
use pyo3::exceptions::{PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::{Py, PyErr, PyResult, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyList, PyTuple};
use rstest::rstest;
use stilyagi_extract::{ExtractError, ExtractSyntax, MarkdownIrFailure};
use stilyagi_ir::RegionKind as IrRegionKind;

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

fn assert_markdown_ir_json_contract(ir_json: &str) {
    let parsed = match serde_json::from_str::<serde_json::Value>(ir_json) {
        Ok(parsed) => parsed,
        Err(error) => panic!("expected parseable IR JSON: {error}"),
    };

    assert_eq!(
        parsed.get("schema_version"),
        Some(&serde_json::json!("1.0.0"))
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
        let syntax_tuple_result = supported_syntaxes_py(py);

        assert!(syntax_tuple_result.is_ok());
        let supported_syntaxes = match syntax_tuple_result {
            Ok(syntax_tuple) => syntax_tuple,
            Err(error) => panic!("unexpected supported_syntaxes failure: {error}"),
        };
        let supported_syntaxes_bound = supported_syntaxes.bind(py);
        let supported_syntax_tuple = supported_syntaxes_bound
            .cast::<PyTuple>()
            .unwrap_or_else(|error| panic!("expected PyTuple but got {error}"));

        assert_eq!(
            supported_syntax_tuple.len().expect("expected tuple length"),
            ExtractSyntax::ALL.len(),
        );
        assert_eq!(
            supported_syntax_tuple
                .get_item(0)
                .expect("missing first syntax")
                .extract::<&str>()
                .expect("expected syntax string"),
            "markdown",
        );
        assert_eq!(
            supported_syntax_tuple
                .get_item(1)
                .expect("missing second syntax")
                .extract::<&str>()
                .expect("expected syntax string"),
            "python_docstring",
        );
        assert_eq!(
            supported_syntax_tuple
                .get_item(2)
                .expect("missing third syntax")
                .extract::<&str>()
                .expect("expected syntax string"),
            "rust_doc_comment",
        );
    });
}

#[rstest]
fn supported_region_kinds_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        let region_tuple_result = supported_region_kinds_py(py);

        assert!(region_tuple_result.is_ok());
        let supported_regions = match region_tuple_result {
            Ok(region_tuple) => region_tuple,
            Err(error) => panic!("unexpected supported_region_kinds failure: {error}"),
        };
        let supported_regions_bound = supported_regions.bind(py);
        let supported_region_tuple = supported_regions_bound
            .cast::<PyTuple>()
            .unwrap_or_else(|error| panic!("expected PyTuple but got {error}"));

        let actual = (0..supported_region_tuple.len().expect("expected tuple length"))
            .map(|index| {
                supported_region_tuple
                    .get_item(index)
                    .expect("missing region kind")
                    .extract::<String>()
                    .expect("expected region kind string")
            })
            .collect::<Vec<_>>();
        let expected = IrRegionKind::ALL
            .iter()
            .copied()
            .map(IrRegionKind::as_str)
            .map(str::to_owned)
            .collect::<Vec<_>>();

        assert_eq!(actual, expected);
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
            .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));
        let regions_any = extracted_document_dict
            .get_item("regions")
            .expect("missing regions payload");
        let ir_json_any = extracted_document_dict
            .get_item("ir_json")
            .expect("missing IR payload");
        let regions = regions_any
            .cast::<PyList>()
            .unwrap_or_else(|error| panic!("expected PyList but got {error}"));
        let first_region_any = regions.get_item(0).expect("missing first region");
        let first_region = first_region_any
            .cast::<PyDict>()
            .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));

        assert_eq!(
            extracted_document_dict
                .get_item("syntax")
                .expect("missing syntax payload")
                .extract::<&str>()
                .expect("expected syntax string"),
            ExtractSyntax::Markdown.as_str(),
        );
        assert_eq!(regions.len().expect("expected list length"), 1,);
        assert_eq!(
            first_region
                .get_item("kind")
                .expect("missing kind payload")
                .extract::<&str>()
                .expect("expected kind string"),
            "heading",
        );
        assert_eq!(
            first_region
                .get_item("text")
                .expect("missing text payload")
                .extract::<&str>()
                .expect("expected text string"),
            "Heading",
        );
        let ir_json = ir_json_any
            .extract::<&str>()
            .expect("expected IR JSON string");
        assert_markdown_ir_json_contract(ir_json);
    });
}

/// Keep rejection behaviour stable for both unsupported and unknown syntax
/// strings.
#[rstest]
#[case("python_docstring", "python_docstring")]
#[case("not_a_syntax", "not_a_syntax")]
fn extract_document_py_rejects_invalid_syntaxes(
    #[case] syntax: &str,
    #[case] expected_fragment: &str,
) {
    let err = invalid_syntax_error(syntax);
    assert!(
        err.to_string().contains(expected_fragment),
        "error message {err:?} did not contain {expected_fragment:?}"
    );
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
fn map_extract_error_uses_value_error_for_unknown_syntax() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::UnknownSyntax("bogus".to_owned()));

        assert!(error.is_instance_of::<PyValueError>(py));
    });
}
