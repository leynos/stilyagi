use super::{extract_document_py, hello};
use pyo3::prelude::{Py, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyList};
use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

struct BridgeState {
    bridge_greeting: Option<&'static str>,
    core_greeting: Option<&'static str>,
    extracted_document: Option<Py<PyDict>>,
    expected_document_text: Option<String>,
}

#[fixture]
fn bridge_state() -> BridgeState {
    BridgeState {
        bridge_greeting: None,
        core_greeting: None,
        extracted_document: None,
        expected_document_text: None,
    }
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when the shared corpus is missing"
)]
fn read_shared_corpus_fixture(relative_path: &str) -> String {
    read_corpus_fixture(relative_path).expect("expected shared corpus fixture to be readable")
}

#[expect(
    clippy::expect_used,
    reason = "test helper stores a verified successful extraction result"
)]
fn perform_extraction(source: &str, syntax: &str, bridge_state: &mut BridgeState) {
    Python::attach(|py| {
        let result = extract_document_py(py, source, syntax);
        assert!(
            result.is_ok(),
            "unexpected extraction failure: {:?}",
            result.err()
        );
        bridge_state.extracted_document = Some(result.expect("result was already verified as Ok"));
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
    perform_extraction("# Heading", "markdown", bridge_state);
    bridge_state.expected_document_text = Some("# Heading".to_owned());
}

#[when("the bridge extracts the shared Markdown fixture")]
fn bridge_extracts_the_shared_markdown_fixture(bridge_state: &mut BridgeState) {
    let source = read_shared_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH);

    perform_extraction(&source, "markdown", bridge_state);
    bridge_state.expected_document_text = Some(source);
}

#[when("the bridge extracts a blank Markdown document")]
fn bridge_extracts_a_blank_markdown_document(bridge_state: &mut BridgeState) {
    perform_extraction("   \n", "markdown", bridge_state);
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
            bridge_state
                .expected_document_text
                .as_deref()
                .unwrap_or_else(|| {
                    panic!("expected_document_text must be provided for this BDD scenario")
                }),
        );
    });
}

#[then("the extracted document preserves the shared Markdown fixture")]
fn extracted_document_preserves_the_shared_markdown_fixture(bridge_state: &BridgeState) {
    extracted_document_preserves_one_source_backed_region(bridge_state);
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
    name = "Bridge extracts the shared Markdown fixture through the Rust boundary"
)]
fn bridge_extracts_the_shared_markdown_fixture_through_the_rust_boundary(
    bridge_state: BridgeState,
) {
    let _ = bridge_state;
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge keeps blank Markdown extraction empty"
)]
fn bridge_keeps_blank_markdown_extraction_empty(bridge_state: BridgeState) {
    let _ = bridge_state;
}
