//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::exceptions::{PyNotImplementedError, PyValueError};
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
    let document = extract_document_from_rust(source, extract_syntax)
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
    Ok(document_dict.unbind())
}

fn map_extract_error(error: &ExtractError) -> PyErr {
    match error {
        ExtractError::UnsupportedSyntax(_) => PyNotImplementedError::new_err(error.to_string()),
        ExtractError::UnknownSyntax(_) => PyValueError::new_err(error.to_string()),
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
mod tests {
    use super::{extract_document_py, hello, supported_syntaxes_py};
    use pyo3::prelude::{Py, Python};
    use pyo3::types::{PyAnyMethods, PyDict, PyList, PyTuple};
    use rstest::{fixture, rstest};
    use rstest_bdd_macros::{given, scenario, then, when};
    use stilyagi_extract::ExtractSyntax;

    struct BridgeState {
        bridge_greeting: Option<&'static str>,
        core_greeting: Option<&'static str>,
        extracted_document: Option<Py<PyDict>>,
    }

    #[fixture]
    fn bridge_state() -> BridgeState {
        BridgeState {
            bridge_greeting: None,
            core_greeting: None,
            extracted_document: None,
        }
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
        });
    }

    #[rstest]
    fn extract_document_py_rejects_unsupported_syntaxes() {
        Python::attach(|py| {
            let error_result = extract_document_py(py, "Example", "python_docstring");

            assert!(error_result.is_err());
            let error = match error_result {
                Ok(document) => panic!("expected unsupported syntax error, got {document:?}"),
                Err(error) => error,
            };
            assert!(error.to_string().contains("python_docstring"));
        });
    }

    #[given("the bridge can call the shared smoke greeting")]
    fn bridge_can_call_the_shared_smoke_greeting(bridge_state: &mut BridgeState) {
        bridge_state.core_greeting = Some(stilyagi_core::smoke_hello());
    }

    #[when("the bridge produces a hello greeting")]
    fn bridge_produces_a_hello_greeting(bridge_state: &mut BridgeState) {
        bridge_state.bridge_greeting = Some(hello());
    }

    #[then("the greeting matches the core crate greeting")]
    fn greeting_matches_the_core_crate_greeting(bridge_state: &BridgeState) {
        assert_eq!(bridge_state.bridge_greeting, bridge_state.core_greeting);
    }

    #[then("the greeting is not the legacy Python fallback")]
    fn greeting_is_not_the_legacy_python_fallback(bridge_state: &BridgeState) {
        assert_ne!(bridge_state.bridge_greeting, Some("hello from Python"));
    }

    #[given("the bridge can call the Rust extraction entrypoint")]
    fn bridge_can_call_the_rust_extraction_entrypoint(bridge_state: &mut BridgeState) {
        let _ = bridge_state;
    }

    #[when("the bridge extracts a Markdown document")]
    fn bridge_extracts_a_markdown_document(bridge_state: &mut BridgeState) {
        Python::attach(|py| {
            let extracted_document_result = extract_document_py(py, "# Heading", "markdown");

            assert!(extracted_document_result.is_ok());
            bridge_state.extracted_document = match extracted_document_result {
                Ok(document) => Some(document),
                Err(error) => panic!("unexpected extraction failure: {error}"),
            };
        });
    }

    #[when("the bridge extracts a blank Markdown document")]
    fn bridge_extracts_a_blank_markdown_document(bridge_state: &mut BridgeState) {
        Python::attach(|py| {
            let extracted_document_result = extract_document_py(py, "   \n", "markdown");

            assert!(extracted_document_result.is_ok());
            bridge_state.extracted_document = match extracted_document_result {
                Ok(document) => Some(document),
                Err(error) => panic!("unexpected extraction failure: {error}"),
            };
        });
    }

    #[then("the extracted document reports Markdown syntax")]
    fn extracted_document_reports_markdown_syntax(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));

        Python::attach(|py| {
            let extracted_document_bound = extracted_document.bind(py);
            let extracted_document_dict = extracted_document_bound
                .cast::<PyDict>()
                .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));

            assert_eq!(
                extracted_document_dict
                    .get_item("syntax")
                    .unwrap_or_else(|error| panic!("missing syntax payload: {error}"))
                    .extract::<&str>()
                    .unwrap_or_else(|error| panic!("expected syntax string: {error}")),
                "markdown",
            );
        });
    }

    #[then("the extracted document preserves one source-backed region")]
    fn extracted_document_preserves_one_source_backed_region(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));

        Python::attach(|py| {
            let extracted_document_bound = extracted_document.bind(py);
            let extracted_document_dict = extracted_document_bound
                .cast::<PyDict>()
                .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));
            let regions_any = extracted_document_dict
                .get_item("regions")
                .unwrap_or_else(|error| panic!("missing regions payload: {error}"));
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
        });
    }

    #[then("the extracted document has no regions")]
    fn extracted_document_has_no_regions(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));

        Python::attach(|py| {
            let extracted_document_bound = extracted_document.bind(py);
            let extracted_document_dict = extracted_document_bound
                .cast::<PyDict>()
                .unwrap_or_else(|error| panic!("expected PyDict but got {error}"));
            let regions_any = extracted_document_dict
                .get_item("regions")
                .unwrap_or_else(|error| panic!("missing regions payload: {error}"));
            let regions = regions_any
                .cast::<PyList>()
                .unwrap_or_else(|error| panic!("expected PyList but got {error}"));

            assert_eq!(
                regions
                    .len()
                    .unwrap_or_else(|error| panic!("expected list length: {error}")),
                0,
            );
        });
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge delegates the smoke greeting to the core crate"
    )]
    fn bridge_delegates_the_smoke_greeting_to_the_core_crate(bridge_state: BridgeState) {
        let _ = bridge_state;
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge greeting is not the legacy Python fallback"
    )]
    fn bridge_greeting_is_not_the_legacy_python_fallback(bridge_state: BridgeState) {
        let _ = bridge_state;
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge extracts a Markdown document through the Rust boundary"
    )]
    fn bridge_extracts_a_markdown_document_through_the_rust_boundary(bridge_state: BridgeState) {
        let _ = bridge_state;
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge keeps blank Markdown extraction empty"
    )]
    fn bridge_keeps_blank_markdown_extraction_empty(bridge_state: BridgeState) {
        let _ = bridge_state;
    }
}
