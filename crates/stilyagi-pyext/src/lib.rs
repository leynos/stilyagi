//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::exceptions::{PyNotImplementedError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};
use stilyagi_core::smoke_hello;
use stilyagi_extract::{
    ExtractError, ExtractSyntax, extract_document as extract_document_from_rust,
};

/// Bridge payload for one extracted prose region.
#[derive(Debug, Clone, PartialEq, Eq)]
struct BridgeRegion {
    kind: String,
    text: String,
}

/// Bridge payload for the first document-shaped extraction result.
#[derive(Debug, Clone, PartialEq, Eq)]
struct BridgeDocument {
    syntax: String,
    regions: Vec<BridgeRegion>,
}

/// Return a simple Rust-side greeting for smoke-testing the extension bridge.
#[pyfunction]
#[expect(
    clippy::missing_const_for_fn,
    reason = "#[pyfunction] requires a normal fn for runtime bindings"
)]
fn hello() -> &'static str {
    smoke_hello()
}

/// Bridge the narrow Rust extraction payload into Python-owned data.
fn bridge_extract_document(source: &str, syntax: &str) -> PyResult<BridgeDocument> {
    let extract_syntax = ExtractSyntax::try_from(syntax).map_err(map_extract_error)?;
    let document = extract_document_from_rust(source, extract_syntax).map_err(map_extract_error)?;
    let regions = document
        .regions()
        .iter()
        .map(|region| BridgeRegion {
            kind: region.kind().to_owned(),
            text: region.text().to_owned(),
        })
        .collect();

    Ok(BridgeDocument {
        syntax: document.syntax().as_str().to_owned(),
        regions,
    })
}

/// Return the minimal extraction payload through the `PyO3` extension boundary.
#[pyfunction(name = "extract_document")]
fn extract_document_py(py: Python<'_>, source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
    let bridge_document = bridge_extract_document(source, syntax)?;
    let document_dict = PyDict::new(py);
    let region_items = bridge_document
        .regions
        .iter()
        .map(|region| {
            let region_dict = PyDict::new(py);
            region_dict.set_item("kind", &region.kind)?;
            region_dict.set_item("text", &region.text)?;
            Ok(region_dict.unbind())
        })
        .collect::<PyResult<Vec<_>>>()?;
    let region_list = PyList::new(py, region_items)?;

    document_dict.set_item("syntax", bridge_document.syntax)?;
    document_dict.set_item("regions", region_list)?;
    Ok(document_dict.unbind())
}

fn map_extract_error(error: ExtractError) -> PyErr {
    match error {
        ExtractError::UnsupportedSyntax(syntax) => {
            PyNotImplementedError::new_err(format!("{syntax} extraction is not implemented yet."))
        }
        ExtractError::UnknownSyntax(syntax) => {
            PyValueError::new_err(format!("unknown syntax '{syntax}'"))
        }
    }
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_document_py, m)?)?;
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{BridgeDocument, bridge_extract_document, hello};
    use rstest::{fixture, rstest};
    use rstest_bdd_macros::{given, scenario, then, when};
    use stilyagi_extract::ExtractSyntax;

    struct BridgeState {
        bridge_greeting: Option<&'static str>,
        core_greeting: Option<&'static str>,
        extracted_document: Option<BridgeDocument>,
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
    fn bridge_extract_document_delegates_to_the_extraction_crate() {
        let bridge_document_result = bridge_extract_document("# Heading", "markdown");

        assert!(bridge_document_result.is_ok());
        let bridge_document = match bridge_document_result {
            Ok(document) => document,
            Err(error) => panic!("unexpected extraction failure: {error}"),
        };
        let first_region = bridge_document.regions.first();

        assert_eq!(bridge_document.syntax, ExtractSyntax::Markdown.as_str());
        assert_eq!(bridge_document.regions.len(), 1);
        assert_eq!(
            first_region.map(|region| region.kind.as_str()),
            Some("document")
        );
        assert_eq!(
            first_region.map(|region| region.text.as_str()),
            Some("# Heading")
        );
    }

    #[rstest]
    fn bridge_extract_document_rejects_unsupported_syntaxes() {
        let error_result = bridge_extract_document("Example", "python_docstring");

        assert!(error_result.is_err());
        let error = match error_result {
            Ok(document) => panic!("expected unsupported syntax error, got {document:?}"),
            Err(error) => error,
        };
        assert!(error.to_string().contains("python_docstring"));
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
        let extracted_document_result = bridge_extract_document("# Heading", "markdown");

        assert!(extracted_document_result.is_ok());
        bridge_state.extracted_document = match extracted_document_result {
            Ok(document) => Some(document),
            Err(error) => panic!("unexpected extraction failure: {error}"),
        };
    }

    #[when("the bridge extracts a blank Markdown document")]
    fn bridge_extracts_a_blank_markdown_document(bridge_state: &mut BridgeState) {
        let extracted_document_result = bridge_extract_document("   \n", "markdown");

        assert!(extracted_document_result.is_ok());
        bridge_state.extracted_document = match extracted_document_result {
            Ok(document) => Some(document),
            Err(error) => panic!("unexpected extraction failure: {error}"),
        };
    }

    #[then("the extracted document reports Markdown syntax")]
    fn extracted_document_reports_markdown_syntax(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));

        assert_eq!(extracted_document.syntax, "markdown");
    }

    #[then("the extracted document preserves one source-backed region")]
    fn extracted_document_preserves_one_source_backed_region(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));
        let first_region = extracted_document.regions.first();

        assert_eq!(extracted_document.regions.len(), 1);
        assert_eq!(
            first_region.map(|region| region.kind.as_str()),
            Some("document")
        );
        assert_eq!(
            first_region.map(|region| region.text.as_str()),
            Some("# Heading")
        );
    }

    #[then("the extracted document has no regions")]
    fn extracted_document_has_no_regions(bridge_state: &BridgeState) {
        let extracted_document = bridge_state
            .extracted_document
            .as_ref()
            .unwrap_or_else(|| panic!("an extracted document should be present"));

        assert!(extracted_document.regions.is_empty());
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
