//! BDD coverage for owner-aware Rust doc-comment extraction.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::IrRegion;
use stilyagi_test_support::{
    FixtureReadError, MALFORMED_RUST_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, read_corpus_fixture,
};

#[derive(Default)]
struct RustDocCommentState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn rust_doc_comment_state() -> RustDocCommentState {
    RustDocCommentState::default()
}

const fn find_extracted_ir(
    rust_doc_comment_state: &RustDocCommentState,
) -> Option<&stilyagi_ir::IrDocument> {
    let Some(document) = rust_doc_comment_state.document.as_ref() else {
        return None;
    };
    document.ir()
}

/// Return the extracted Rust IR or report the missing extraction step.
fn extracted_ir(
    rust_doc_comment_state: &RustDocCommentState,
) -> Result<&stilyagi_ir::IrDocument, &'static str> {
    find_extracted_ir(rust_doc_comment_state)
        .ok_or("expected an extracted Rust IR payload; did the extraction step run?")
}

fn rust_doc_comment_regions(ir: &stilyagi_ir::IrDocument) -> Vec<&IrRegion> {
    ir.regions
        .iter()
        .filter(|region| region.kind == "rust_doc_comment")
        .collect()
}

/// Missing BDD extraction state is reported without panicking.
#[test]
fn missing_extraction_state_returns_an_error() {
    let state = RustDocCommentState::default();
    assert_eq!(
        extracted_ir(&state).expect_err("missing extraction should return an error"),
        "expected an extracted Rust IR payload; did the extraction step run?"
    );
}

#[given("a Rust source file with crate, type, and function doc comments")]
fn a_rust_source_file_with_crate_type_and_function_doc_comments(
    rust_doc_comment_state: &mut RustDocCommentState,
) -> Result<(), FixtureReadError> {
    rust_doc_comment_state.source = Some(read_corpus_fixture(SHARED_RUST_FIXTURE_PATH)?);
    Ok(())
}

#[given("a Rust source file whose function body never closes")]
fn a_rust_source_file_whose_function_body_never_closes(
    rust_doc_comment_state: &mut RustDocCommentState,
) -> Result<(), FixtureReadError> {
    rust_doc_comment_state.source = Some(read_corpus_fixture(MALFORMED_RUST_FIXTURE_PATH)?);
    Ok(())
}

#[when("the extractor runs for the rust_doc_comment syntax")]
fn the_extractor_runs_for_the_rust_doc_comment_syntax(
    rust_doc_comment_state: &mut RustDocCommentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let source = rust_doc_comment_state
        .source
        .as_deref()
        .ok_or("expected Rust source to be configured")?;

    rust_doc_comment_state.document =
        Some(extract_document(source, ExtractSyntax::RustDocComment)?);
    Ok(())
}

#[then("each doc-comment region records its prose text")]
fn each_doc_comment_region_records_its_prose_text(
    rust_doc_comment_state: &RustDocCommentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(rust_doc_comment_state)?;
    let texts = rust_doc_comment_regions(ir)
        .into_iter()
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>();

    assert_eq!(
        texts,
        vec![
            " Crate-level documentation comment for the shared Stilyagi corpus.",
            " Item-level documentation comment used by later Rust extraction slices.",
            " Method documentation comment with extractable prose.",
            " Function documentation comment after a suppression marker.",
        ],
    );
    Ok(())
}

#[then("each doc-comment region records its owning item kind and qualified name")]
fn each_doc_comment_region_records_its_owning_item_kind_and_qualified_name(
    rust_doc_comment_state: &RustDocCommentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(rust_doc_comment_state)?;
    let maybe_owners = rust_doc_comment_regions(ir)
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
        panic!("expected every Rust region to record owner metadata");
    };

    assert_eq!(
        owners,
        vec![
            ("module", None, None),
            ("struct", Some("FixtureExample"), Some("FixtureExample")),
            (
                "function",
                Some("documented_value"),
                Some("FixtureExample::documented_value"),
            ),
            (
                "function",
                Some("fixture_function"),
                Some("fixture_function"),
            ),
        ],
    );
    Ok(())
}

#[then("the crate documentation comment is still extracted")]
fn the_crate_documentation_comment_is_still_extracted(
    rust_doc_comment_state: &RustDocCommentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(rust_doc_comment_state)?;
    let regions = rust_doc_comment_regions(ir);

    assert_eq!(regions.len(), 1);
    let Some(region) = regions.first() else {
        panic!("expected malformed Rust crate doc-comment");
    };
    assert_eq!(
        region.text,
        " Crate-level documentation before malformed Rust source."
    );
    let Some(owner) = region.owner.as_ref() else {
        panic!("expected module owner metadata");
    };
    assert_eq!(owner.kind, "module");
    assert_eq!(owner.name, None);
    assert_eq!(owner.qualname, None);
    Ok(())
}

#[then("a recoverable Rust parse error is recorded")]
fn a_recoverable_rust_parse_error_is_recorded(
    rust_doc_comment_state: &RustDocCommentState,
) -> Result<(), Box<dyn std::error::Error>> {
    let ir = extracted_ir(rust_doc_comment_state)?;

    assert_ne!(ir.errors, []);
    assert!(
        ir.errors
            .iter()
            .any(|error| error.code == "rust-parse-recovery")
    );
    Ok(())
}

#[scenario(
    path = "tests/features/rust_doc_comment_extraction.feature",
    name = "Extract documentation comments with their owning items"
)]
fn extract_documentation_comments_with_their_owning_items(
    #[from(rust_doc_comment_state)] _rust_doc_comment_state: RustDocCommentState,
) {
}

#[scenario(
    path = "tests/features/rust_doc_comment_extraction.feature",
    name = "Recover from a malformed Rust file"
)]
fn recover_from_a_malformed_rust_file(
    #[from(rust_doc_comment_state)] _rust_doc_comment_state: RustDocCommentState,
) {
}
