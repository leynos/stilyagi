//! BDD coverage for owner-aware Python docstring extraction.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::IrRegion;
use stilyagi_test_support::{
    MALFORMED_PYTHON_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH, read_corpus_fixture,
};

#[derive(Default)]
struct PythonDocstringState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn python_docstring_state() -> PythonDocstringState {
    PythonDocstringState::default()
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when the shared corpus is missing"
)]
fn read_python_fixture(relative_path: &str) -> String {
    read_corpus_fixture(relative_path).expect("expected Python fixture to be readable")
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when a BDD extraction step did not run"
)]
#[expect(
    clippy::missing_const_for_fn,
    reason = "CodeRabbit requested a regular test helper because it relies on runtime panic paths"
)]
fn extracted_ir(python_docstring_state: &PythonDocstringState) -> &stilyagi_ir::IrDocument {
    python_docstring_state
        .document
        .as_ref()
        .expect("expected extracted document")
        .ir()
        .expect("expected extracted Python IR")
}

fn python_docstring_regions(ir: &stilyagi_ir::IrDocument) -> Vec<&IrRegion> {
    ir.regions
        .iter()
        .filter(|region| region.kind == "python_docstring")
        .collect()
}

#[given("a Python source file with module, class, and function docstrings")]
fn a_python_source_file_with_module_class_and_function_docstrings(
    python_docstring_state: &mut PythonDocstringState,
) {
    python_docstring_state.source = Some(read_python_fixture(SHARED_PYTHON_FIXTURE_PATH));
}

#[given("a Python source file whose function signature never closes")]
fn a_python_source_file_whose_function_signature_never_closes(
    python_docstring_state: &mut PythonDocstringState,
) {
    python_docstring_state.source = Some(read_python_fixture(MALFORMED_PYTHON_FIXTURE_PATH));
}

#[when("the extractor runs for the python_docstring syntax")]
#[expect(
    clippy::expect_used,
    reason = "BDD test step should fail loudly when setup or extraction fails"
)]
fn the_extractor_runs_for_the_python_docstring_syntax(
    python_docstring_state: &mut PythonDocstringState,
) {
    let source = python_docstring_state
        .source
        .as_deref()
        .expect("expected Python source to be configured");

    python_docstring_state.document = Some(
        extract_document(source, ExtractSyntax::PythonDocstring)
            .expect("expected Python extraction to succeed"),
    );
}

#[then("each docstring region records its prose text")]
fn each_docstring_region_records_its_prose_text(python_docstring_state: &PythonDocstringState) {
    let ir = extracted_ir(python_docstring_state);
    let texts = python_docstring_regions(ir)
        .into_iter()
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>();

    assert_eq!(
        texts,
        vec![
            "Module docstring for the shared Stilyagi corpus.",
            "Class docstring with prose for extraction tests.",
            "Return a documented value from a method docstring.",
            "Use a function docstring for later Python extraction slices.",
        ],
    );
}

#[then("each docstring region records its owning symbol kind and qualified name")]
#[expect(
    clippy::expect_used,
    reason = "BDD assertion should fail loudly when owner metadata is absent"
)]
fn each_docstring_region_records_its_owning_symbol_kind_and_qualified_name(
    python_docstring_state: &PythonDocstringState,
) {
    let ir = extracted_ir(python_docstring_state);
    let owners = python_docstring_regions(ir)
        .into_iter()
        .map(|region| {
            let owner = region
                .owner
                .as_ref()
                .expect("expected Python docstring owner");
            (
                owner.kind.as_str(),
                owner.name.as_deref(),
                owner.qualname.as_deref(),
            )
        })
        .collect::<Vec<_>>();

    assert_eq!(
        owners,
        vec![
            ("module", None, None),
            ("class", Some("FixtureExample"), Some("FixtureExample")),
            ("function", Some("method"), Some("FixtureExample.method")),
            (
                "function",
                Some("fixture_function"),
                Some("fixture_function"),
            ),
        ],
    );
}

#[then("the module docstring is still extracted")]
#[expect(
    clippy::expect_used,
    reason = "BDD assertion should fail loudly when the expected region is absent"
)]
fn the_module_docstring_is_still_extracted(python_docstring_state: &PythonDocstringState) {
    let ir = extracted_ir(python_docstring_state);
    let regions = python_docstring_regions(ir);

    assert_eq!(regions.len(), 1);
    let region = regions
        .first()
        .expect("expected malformed Python module docstring");
    assert_eq!(
        region.text,
        "Module docstring before malformed Python source."
    );
    let owner = region
        .owner
        .as_ref()
        .expect("expected module owner metadata");
    assert_eq!(owner.kind, "module");
    assert!(owner.name.is_none());
    assert!(owner.qualname.is_none());
}

#[then("a recoverable parse error is recorded")]
fn a_recoverable_parse_error_is_recorded(python_docstring_state: &PythonDocstringState) {
    let ir = extracted_ir(python_docstring_state);

    assert!(!ir.errors.is_empty());
    assert!(
        ir.errors
            .iter()
            .any(|error| error.code == "python-parse-recovery")
    );
}

#[scenario(
    path = "tests/features/python_docstring_extraction.feature",
    name = "Extract docstrings with their owning symbols"
)]
fn extract_docstrings_with_their_owning_symbols(
    #[from(python_docstring_state)] _python_docstring_state: PythonDocstringState,
) {
}

#[scenario(
    path = "tests/features/python_docstring_extraction.feature",
    name = "Recover from a malformed Python file"
)]
fn recover_from_a_malformed_python_file(
    #[from(python_docstring_state)] _python_docstring_state: PythonDocstringState,
) {
}
