//! BDD coverage for owner-aware Python docstring extraction.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::IrRegion;
use stilyagi_test_support::{
    FixtureReadError, MALFORMED_PYTHON_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH,
    read_corpus_fixture,
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

const fn find_extracted_ir(
    python_docstring_state: &PythonDocstringState,
) -> Option<&stilyagi_ir::IrDocument> {
    let Some(document) = python_docstring_state.document.as_ref() else {
        return None;
    };
    document.ir()
}

/// Return the extracted Python IR or report the missing extraction step.
fn extracted_ir(
    python_docstring_state: &PythonDocstringState,
) -> Result<&stilyagi_ir::IrDocument, &'static str> {
    find_extracted_ir(python_docstring_state)
        .ok_or("expected an extracted Python IR payload; did the extraction step run?")
}

fn python_docstring_regions(ir: &stilyagi_ir::IrDocument) -> Vec<&IrRegion> {
    ir.regions
        .iter()
        .filter(|region| region.kind == "python_docstring")
        .collect()
}

/// Missing BDD extraction state is reported without panicking.
#[test]
fn missing_extraction_state_returns_an_error() {
    let state = PythonDocstringState::default();
    assert_eq!(
        extracted_ir(&state).expect_err("missing extraction should return an error"),
        "expected an extracted Python IR payload; did the extraction step run?"
    );
}

#[given("a Python source file with module, class, and function docstrings")]
fn a_python_source_file_with_module_class_and_function_docstrings(
    python_docstring_state: &mut PythonDocstringState,
) -> Result<(), FixtureReadError> {
    python_docstring_state.source = Some(read_corpus_fixture(SHARED_PYTHON_FIXTURE_PATH)?);
    Ok(())
}

#[given("a Python source file whose function signature never closes")]
fn a_python_source_file_whose_function_signature_never_closes(
    python_docstring_state: &mut PythonDocstringState,
) -> Result<(), FixtureReadError> {
    python_docstring_state.source = Some(read_corpus_fixture(MALFORMED_PYTHON_FIXTURE_PATH)?);
    Ok(())
}

#[when("the extractor runs for the python_docstring syntax")]
fn the_extractor_runs_for_the_python_docstring_syntax(
    python_docstring_state: &mut PythonDocstringState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = python_docstring_state
        .source
        .as_deref()
        .ok_or("expected Python source to be configured")?;

    python_docstring_state.document =
        Some(extract_document(source, ExtractSyntax::PythonDocstring)?);
    Ok(())
}

#[then("each docstring region records its prose text")]
fn each_docstring_region_records_its_prose_text(
    python_docstring_state: &PythonDocstringState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(python_docstring_state)?;
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
    Ok(())
}

#[then("each docstring region records its owning symbol kind and qualified name")]
fn each_docstring_region_records_its_owning_symbol_kind_and_qualified_name(
    python_docstring_state: &PythonDocstringState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(python_docstring_state)?;
    let maybe_owners = python_docstring_regions(ir)
        .into_iter()
        .map(|region| {
            region.owner.as_ref().map(|owner| {
                (
                    owner.kind.as_str(),
                    owner.name.as_deref(),
                    owner.qualname.as_deref(),
                )
            })
        })
        .collect::<Option<Vec<_>>>();
    let Some(owners) = maybe_owners else {
        panic!("expected every Python region to record owner metadata");
    };

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
    Ok(())
}

#[then("the module docstring is still extracted")]
fn the_module_docstring_is_still_extracted(
    python_docstring_state: &PythonDocstringState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(python_docstring_state)?;
    let regions = python_docstring_regions(ir);

    assert_eq!(regions.len(), 1);
    let Some(region) = regions.first() else {
        panic!("expected malformed Python module docstring");
    };
    assert_eq!(
        region.text,
        "Module docstring before malformed Python source."
    );
    let Some(owner) = region.owner.as_ref() else {
        panic!("expected module owner metadata");
    };
    assert_eq!(owner.kind, "module");
    assert_eq!(owner.name, None);
    assert_eq!(owner.qualname, None);
    Ok(())
}

#[then("a recoverable parse error is recorded")]
fn a_recoverable_parse_error_is_recorded(
    python_docstring_state: &PythonDocstringState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(python_docstring_state)?;

    assert_ne!(ir.errors, []);
    assert!(
        ir.errors
            .iter()
            .any(|error| error.code == "python-parse-recovery")
    );
    Ok(())
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
