//! Error-mapping tests for the `PyO3` bridge.
//!
//! These pin which Python exception type each extraction failure surfaces as,
//! so a Python caller can catch the documented class rather than a generic
//! `Exception`.

use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::Python,
};
use rstest::rstest;

use super::{
    ExtractError,
    MarkdownIrFailure,
    PythonExtractError,
    bridge_extract_document,
    map_extract_error,
};

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

/// Markdown IR failures must surface to Python as `RuntimeError`.
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

/// Python IR failures must surface as `RuntimeError` with the crate's wording.
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

/// An unrecognized syntax string must surface as `ValueError`.
#[rstest]
fn map_extract_error_uses_value_error_for_unknown_syntax() {
    Python::attach(|py| {
        let error = map_extract_error(&ExtractError::UnknownSyntax("bogus".to_owned()));

        assert!(error.is_instance_of::<PyValueError>(py));
    });
}
