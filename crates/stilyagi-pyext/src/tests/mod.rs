//! Tests for the Python extension bridge payload and error mapping.

pub(crate) mod payload;
mod rust_doc_comment;

use super::{
    authored_directive_error_codes_py, extract_document_function, extract_document_py, hello,
    map_extract_error, supported_region_kinds_py, supported_syntaxes_py,
};
use payload::{
    dict_list, dict_string, list_dict_at, parse_ir_json, region_kind_and_text, tuple_strings,
};
use pyo3::exceptions::{PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::{Py, PyResult, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyListMethods, PyTuple};
use rstest::rstest;
use stilyagi_extract::{
    ExtractError, ExtractSyntax, MarkdownIrFailure, PythonExtractError, RustExtractError,
};
use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, RegionKind as IrRegionKind};

fn bridge_extract_document(source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
    Python::attach(|py| {
        let args = PyTuple::new(py, [source, syntax])?;
        extract_document_py(py, &args)
    })
}

/// Name every violated clause of the canonical IR JSON envelope contract.
fn ir_contract_violations(parsed: &serde_json::Value) -> Vec<&'static str> {
    let has_schema_version = parsed.get("schema_version") == Some(&serde_json::json!("1.1.0"));
    let has_document_object = parsed
        .get("document")
        .is_some_and(serde_json::Value::is_object);
    let line_index_starts_at_zero = parsed
        .get("line_index")
        .and_then(serde_json::Value::as_array)
        .and_then(|line_index| line_index.first())
        == Some(&serde_json::json!(0));
    let has_regions_array = parsed
        .get("regions")
        .is_some_and(serde_json::Value::is_array);

    [
        (has_schema_version, "schema_version must be 1.1.0"),
        (has_document_object, "document must be an object"),
        (line_index_starts_at_zero, "line_index must start at 0"),
        (has_regions_array, "regions must be an array"),
    ]
    .into_iter()
    .filter_map(|(is_satisfied, clause)| (!is_satisfied).then_some(clause))
    .collect()
}

#[track_caller]
fn assert_ir_json_contract(parsed: &serde_json::Value) {
    assert_eq!(
        ir_contract_violations(parsed),
        [] as [&str; 0],
        "IR JSON contract"
    );
}

fn expected_strings<'a>(values: impl IntoIterator<Item = &'a str>) -> Vec<String> {
    values.into_iter().map(str::to_owned).collect()
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
        let expected = expected_strings(
            ExtractSyntax::ALL
                .iter()
                .copied()
                .map(ExtractSyntax::as_str),
        );
        let actual = tuple_strings(py, supported_syntaxes_py(py))
            .expect("supported_syntaxes should return a tuple of strings");

        assert_eq!(actual, expected);
    });
}

#[rstest]
fn supported_region_kinds_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        let expected =
            expected_strings(IrRegionKind::ALL.iter().copied().map(IrRegionKind::as_str));
        let actual = tuple_strings(py, supported_region_kinds_py(py))
            .expect("supported_region_kinds should return a tuple of strings");

        assert_eq!(actual, expected);
    });
}

#[rstest]
fn authored_directive_error_codes_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        let expected = expected_strings(AUTHORED_DIRECTIVE_ERROR_CODES.iter().copied());
        let actual = tuple_strings(py, authored_directive_error_codes_py(py))
            .expect("authored_directive_error_codes should return a tuple of strings");

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
        let extracted = extract_document_py(py, &args).expect("Markdown extraction should succeed");
        let document = extracted.bind(py);
        let regions = dict_list(document, "regions").expect("Markdown regions should be a list");
        let first_region =
            list_dict_at(&regions, 0).expect("first Markdown region should be a dict");

        assert_eq!(
            dict_string(document, "syntax").expect("syntax payload should be a string"),
            ExtractSyntax::Markdown.as_str(),
        );
        assert_eq!(regions.len(), 1);
        assert_eq!(
            region_kind_and_text(&first_region).expect("region should carry kind and text"),
            ("heading".to_owned(), "Heading".to_owned()),
        );
        let ir_json = dict_string(document, "ir_json").expect("IR payload should be a string");
        let parsed = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
        assert_ir_json_contract(&parsed);
    });
}

#[rstest]
fn extract_document_py_exposes_python_docstrings() {
    let source = "\"\"\"Module docs.\"\"\"\n\ndef example():\n    \"\"\"Function docs.\"\"\"\n";
    let document = bridge_extract_document(source, "python_docstring")
        .expect("Python docstring extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions = dict_list(document_dict, "regions").expect("Python regions should be a list");
        let region_summaries = (0..regions.len())
            .map(|index| {
                let region = list_dict_at(&regions, index).expect("region should be a dict");
                region_kind_and_text(&region).expect("region should carry kind and text")
            })
            .collect::<Vec<_>>();

        assert_eq!(
            dict_string(document_dict, "syntax").expect("syntax payload should be a string"),
            ExtractSyntax::PythonDocstring.as_str(),
        );
        assert_eq!(
            region_summaries,
            [
                ("python_docstring".to_owned(), "Module docs.".to_owned()),
                ("python_docstring".to_owned(), "Function docs.".to_owned()),
            ],
        );

        let ir_json = dict_string(document_dict, "ir_json").expect("IR payload should be a string");
        let parsed = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
        assert_ir_json_contract(&parsed);
    });
}

/// Keep rejection behaviour stable for both unsupported and unknown syntax
/// strings.
#[rstest]
#[case("not_a_syntax", "not_a_syntax")]
fn extract_document_py_rejects_invalid_syntaxes(
    #[case] syntax: &str,
    #[case] expected_fragment: &str,
) {
    let err = bridge_extract_document("Example", syntax)
        .expect_err(&format!("expected an error for syntax {syntax:?}"));
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
    let error = bridge_extract_document("example", "not_a_real_syntax")
        .expect_err("expected unknown syntax error");

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
