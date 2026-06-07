//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::exceptions::{PyNotImplementedError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule, PyTuple};
use stilyagi_core::smoke_hello;
use stilyagi_extract::{
    ExtractError, ExtractSyntax, extract_document as extract_document_from_rust,
};

/// Return a simple Rust-side greeting for smoke-testing the extension bridge.
#[pyfunction]
#[expect(
    clippy::missing_const_for_fn,
    reason = "#[pyfunction] requires a normal fn for runtime bindings"
)]
fn hello() -> &'static str {
    smoke_hello()
}

/// Return the stable syntax spellings exported by the Rust bridge.
#[pyfunction(name = "supported_syntaxes")]
fn supported_syntaxes_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    let syntax_items = ExtractSyntax::ALL
        .into_iter()
        .map(ExtractSyntax::as_str)
        .collect::<Vec<_>>();

    Ok(PyTuple::new(py, syntax_items)?.unbind())
}

/// Return the minimal extraction payload through the `PyO3` extension boundary.
#[pyfunction(name = "extract_document")]
fn extract_document_py(py: Python<'_>, source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
    let extract_syntax =
        ExtractSyntax::try_from(syntax).map_err(|error| map_extract_error(&error))?;
    let document = py
        .detach(|| extract_document_from_rust(source, extract_syntax))
        .map_err(|error| map_extract_error(&error))?;
    let document_dict = PyDict::new(py);
    let region_items = document
        .regions()
        .iter()
        .map(|region| {
            let region_dict = PyDict::new(py);
            region_dict.set_item("kind", region.kind())?;
            region_dict.set_item("text", region.text())?;
            Ok(region_dict.unbind())
        })
        .collect::<PyResult<Vec<_>>>()?;
    let region_list = PyList::new(py, region_items)?;

    document_dict.set_item("syntax", document.syntax().as_str())?;
    document_dict.set_item("regions", region_list)?;
    if let Some(ir) = document.ir() {
        let ir_json = ir
            .to_canonical_json()
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        document_dict.set_item("ir_json", ir_json)?;
    }
    Ok(document_dict.unbind())
}

fn map_extract_error(error: &ExtractError) -> PyErr {
    match error {
        ExtractError::UnsupportedSyntax(_) => PyNotImplementedError::new_err(error.to_string()),
        ExtractError::UnknownSyntax(_) => PyValueError::new_err(error.to_string()),
        ExtractError::MarkdownIr(_) => PyRuntimeError::new_err(error.to_string()),
    }
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_document_py, m)?)?;
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    m.add_function(wrap_pyfunction!(supported_syntaxes_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod bridge_bdd;

#[cfg(test)]
mod tests {
    use super::{extract_document_py, hello, map_extract_error, supported_syntaxes_py};
    use pyo3::exceptions::{PyRuntimeError, PyValueError};
    use pyo3::prelude::{Py, PyErr, PyResult, Python};
    use pyo3::types::{PyAnyMethods, PyDict, PyList, PyTuple};
    use rstest::rstest;
    use stilyagi_extract::{ExtractError, ExtractSyntax};

    fn bridge_extract_document(source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
        Python::attach(|py| extract_document_py(py, source, syntax))
    }

    #[expect(
        clippy::expect_used,
        reason = "test helper should fail loudly when invalid syntax unexpectedly succeeds"
    )]
    fn invalid_syntax_error(syntax: &str) -> PyErr {
        bridge_extract_document("Example", syntax)
            .expect_err(&format!("expected an error for syntax {syntax:?}"))
    }

    fn assert_markdown_ir_json_contract(ir_json: &str) {
        let parsed = serde_json::from_str::<serde_json::Value>(ir_json)
            .unwrap_or_else(|error| panic!("expected parseable IR JSON: {error}"));

        assert_eq!(
            parsed.get("schema_version"),
            Some(&serde_json::json!("1.0.0"))
        );
        assert!(
            parsed
                .get("document")
                .is_some_and(serde_json::Value::is_object)
        );

        let line_index = parsed
            .get("line_index")
            .and_then(serde_json::Value::as_array)
            .unwrap_or_else(|| panic!("expected line_index array"));
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
                supported_syntax_tuple
                    .len()
                    .unwrap_or_else(|error| panic!("expected tuple length: {error}")),
                ExtractSyntax::ALL.len(),
            );
            assert_eq!(
                supported_syntax_tuple
                    .get_item(0)
                    .unwrap_or_else(|error| panic!("missing first syntax: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected syntax string: {error}")),
                "markdown",
            );
            assert_eq!(
                supported_syntax_tuple
                    .get_item(1)
                    .unwrap_or_else(|error| panic!("missing second syntax: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected syntax string: {error}")),
                "python_docstring",
            );
            assert_eq!(
                supported_syntax_tuple
                    .get_item(2)
                    .unwrap_or_else(|error| panic!("missing third syntax: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected syntax string: {error}")),
                "rust_doc_comment",
            );
        });
    }

    #[rstest]
    fn extract_document_py_exposes_markdown_document() {
        Python::attach(|py| {
            let document_result = extract_document_py(py, "# Heading", "markdown");

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
                .unwrap_or_else(|error| panic!("missing regions payload: {error}"));
            let ir_json_any = extracted_document_dict
                .get_item("ir_json")
                .unwrap_or_else(|error| panic!("missing IR payload: {error}"));
            let regions = regions_any
                .cast::<PyList>()
                .unwrap_or_else(|error| panic!("expected PyList but got {error}"));
            let first_region_any = regions
                .get_item(0)
                .unwrap_or_else(|error| panic!("missing first region: {error}"));
            let first_region = first_region_any
                .cast::<PyDict>()
                .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));

            assert_eq!(
                extracted_document_dict
                    .get_item("syntax")
                    .unwrap_or_else(|error| panic!("missing syntax payload: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected syntax string: {error}")),
                ExtractSyntax::Markdown.as_str(),
            );
            assert_eq!(
                regions
                    .len()
                    .unwrap_or_else(|error| panic!("expected list length: {error}")),
                1,
            );
            assert_eq!(
                first_region
                    .get_item("kind")
                    .unwrap_or_else(|error| panic!("missing kind payload: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected kind string: {error}")),
                "document",
            );
            assert_eq!(
                first_region
                    .get_item("text")
                    .unwrap_or_else(|error| panic!("missing text payload: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected text string: {error}")),
                "# Heading",
            );
            let ir_json = ir_json_any
                .extract::<&str>()
                .unwrap_or_else(|error| panic!("expected IR JSON string: {error}"));
            assert_markdown_ir_json_contract(ir_json);
        });
    }

    /// Keep rejection behaviour stable for both unsupported and unknown
    /// syntax strings.
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
    /// `PyValueError` so Python callers receive a `ValueError` for
    /// unrecognised syntax strings.
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
            let error = map_extract_error(&ExtractError::MarkdownIr("bad IR".to_owned()));

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
}
