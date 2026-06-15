//! Tests for Python docstring extraction.

use rstest::rstest;
use stilyagi_ir::SourceIdentity;
use stilyagi_test_support::read_corpus_fixture;

use super::python_docstring_ir_document;

const SHARED_PYTHON_FIXTURE: &str =
    "tests/fixtures/corpus/python/valid/module-class-function-docstrings.py";
const NESTED_PYTHON_FIXTURE: &str = "tests/fixtures/corpus/python/valid/nested-declarations.py";
const EDGE_CASE_PYTHON_FIXTURE: &str = "tests/fixtures/corpus/python/valid/docstring-edge-cases.py";
const MALFORMED_PYTHON_FIXTURE: &str =
    "tests/fixtures/corpus/python/malformed/unclosed-function.py.txt";

fn extract_python(source: &str) -> stilyagi_ir::IrDocument {
    match python_docstring_ir_document(source, SourceIdentity::anonymous()) {
        Ok(document) => document,
        Err(error) => panic!("expected Python extraction: {error:?}"),
    }
}

fn fixture_document(path: &str) -> stilyagi_ir::IrDocument {
    let source = match read_corpus_fixture(path) {
        Ok(source) => source,
        Err(error) => panic!("expected Python fixture {path}: {error}"),
    };

    extract_python(&source)
}

#[rstest]
fn shared_fixture_extracts_owner_metadata() {
    let document = fixture_document(SHARED_PYTHON_FIXTURE);
    let owners = document
        .regions
        .iter()
        .map(|region| {
            let owner = region
                .owner
                .as_ref()
                .unwrap_or_else(|| panic!("expected docstring owner"));
            (
                region.text.as_str(),
                owner.kind.as_str(),
                owner.name.as_deref(),
                owner.qualname.as_deref(),
            )
        })
        .collect::<Vec<_>>();

    assert_eq!(document.document.syntax, "python");
    assert_eq!(document.regions.len(), 4);
    assert_eq!(
        owners,
        vec![
            (
                "Module docstring for the shared Stilyagi corpus.",
                "module",
                None,
                None,
            ),
            (
                "Class docstring with prose for extraction tests.",
                "class",
                Some("FixtureExample"),
                Some("FixtureExample"),
            ),
            (
                "Return a documented value from a method docstring.",
                "function",
                Some("method"),
                Some("FixtureExample.method"),
            ),
            (
                "Use a function docstring for later Python extraction slices.",
                "function",
                Some("fixture_function"),
                Some("fixture_function"),
            ),
        ]
    );
    assert!(
        document
            .regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );
}

#[rstest]
fn nested_fixture_uses_python_qualname_semantics() {
    let document = fixture_document(NESTED_PYTHON_FIXTURE);
    let qualnames = document
        .regions
        .iter()
        .filter_map(|region| region.owner.as_ref()?.qualname.as_deref())
        .collect::<Vec<_>>();

    assert!(qualnames.contains(&"outer_function.<locals>.inner_function"));
    assert!(qualnames.contains(&"outer_function.<locals>.LocalClass"));
    assert!(qualnames.contains(&"outer_function.<locals>.LocalClass.method"));
    assert!(qualnames.contains(&"DecoratedExample.from_value"));
    assert!(qualnames.contains(&"DecoratedExample.doubly_decorated"));
    assert!(qualnames.contains(&"async_function"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_if"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_for"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_with"));
}

#[rstest]
fn edge_case_fixture_preserves_verbatim_content_and_rejects_non_docstrings() {
    let document = fixture_document(EDGE_CASE_PYTHON_FIXTURE);
    let texts = document
        .regions
        .iter()
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>();

    assert!(texts.contains(&"Line one.\n\n    Line two.\n    "));
    assert!(texts.contains(&r"Keep \n and \t escapes verbatim."));
    assert!(texts.contains(&r#"Mention "double quotes", 'single quotes', and a \\ backslash."#));
    assert!(texts.contains(&""));
    assert!(texts.contains(&"   "));
    assert!(!texts.iter().any(|text| text.contains("Not a v1 docstring")));
}

#[rstest]
fn crlf_docstring_reconstructs_exactly() {
    let source = "def crlf():\r\n    \"\"\"line one\r\n    line two\"\"\"\r\n";
    let document = extract_python(source);
    let region = document
        .regions
        .first()
        .unwrap_or_else(|| panic!("expected CR-LF docstring region"));

    assert_eq!(region.text, "line one\r\n    line two");
    assert!(region.segments_reconstruct_text());
}

#[rstest]
fn malformed_fixture_yields_partial_ir_and_errors() {
    let document = fixture_document(MALFORMED_PYTHON_FIXTURE);

    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        document.regions.first().map(|region| region.text.as_str()),
        Some("Module docstring before malformed Python source.")
    );
    assert!(!document.errors.is_empty());
}
