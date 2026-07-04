//! BDD coverage for owner-aware Rust doc-comment extraction.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::IrRegion;
use stilyagi_test_support::{
    MALFORMED_RUST_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, read_corpus_fixture,
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

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when the shared corpus is missing"
)]
fn read_rust_fixture(relative_path: &str) -> String {
    read_corpus_fixture(relative_path).expect("expected Rust fixture to be readable")
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when a BDD extraction step did not run"
)]
#[expect(
    clippy::missing_const_for_fn,
    reason = "cannot be const: the access chain uses the non-const Option::expect and ExtractDocument::ir"
)]
fn extracted_ir(rust_doc_comment_state: &RustDocCommentState) -> &stilyagi_ir::IrDocument {
    rust_doc_comment_state
        .document
        .as_ref()
        .expect("expected extracted document")
        .ir()
        .expect("expected extracted Rust IR")
}

fn rust_doc_comment_regions(ir: &stilyagi_ir::IrDocument) -> Vec<&IrRegion> {
    ir.regions
        .iter()
        .filter(|region| region.kind == "rust_doc_comment")
        .collect()
}

#[given("a Rust source file with crate, type, and function doc comments")]
fn a_rust_source_file_with_crate_type_and_function_doc_comments(
    rust_doc_comment_state: &mut RustDocCommentState,
) {
    rust_doc_comment_state.source = Some(read_rust_fixture(SHARED_RUST_FIXTURE_PATH));
}

#[given("a Rust source file whose function body never closes")]
fn a_rust_source_file_whose_function_body_never_closes(
    rust_doc_comment_state: &mut RustDocCommentState,
) {
    rust_doc_comment_state.source = Some(read_rust_fixture(MALFORMED_RUST_FIXTURE_PATH));
}

#[when("the extractor runs for the rust_doc_comment syntax")]
#[expect(
    clippy::expect_used,
    reason = "BDD test step should fail loudly when setup or extraction fails"
)]
fn the_extractor_runs_for_the_rust_doc_comment_syntax(
    rust_doc_comment_state: &mut RustDocCommentState,
) {
    let source = rust_doc_comment_state
        .source
        .as_deref()
        .expect("expected Rust source to be configured");

    rust_doc_comment_state.document = Some(
        extract_document(source, ExtractSyntax::RustDocComment)
            .expect("expected Rust extraction to succeed"),
    );
}

#[then("each doc-comment region records its prose text")]
fn each_doc_comment_region_records_its_prose_text(rust_doc_comment_state: &RustDocCommentState) {
    let ir = extracted_ir(rust_doc_comment_state);
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
}

#[then("each doc-comment region records its owning item kind and qualified name")]
#[expect(
    clippy::expect_used,
    reason = "BDD assertion should fail loudly when owner metadata is absent"
)]
fn each_doc_comment_region_records_its_owning_item_kind_and_qualified_name(
    rust_doc_comment_state: &RustDocCommentState,
) {
    let ir = extracted_ir(rust_doc_comment_state);
    let owners = rust_doc_comment_regions(ir)
        .into_iter()
        .map(|region| {
            let owner = region
                .owner
                .as_ref()
                .expect("expected Rust doc-comment owner");
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
}

#[then("the crate documentation comment is still extracted")]
#[expect(
    clippy::expect_used,
    reason = "BDD assertion should fail loudly when the expected region is absent"
)]
fn the_crate_documentation_comment_is_still_extracted(
    rust_doc_comment_state: &RustDocCommentState,
) {
    let ir = extracted_ir(rust_doc_comment_state);
    let regions = rust_doc_comment_regions(ir);

    assert_eq!(regions.len(), 1);
    let region = regions
        .first()
        .expect("expected malformed Rust crate doc-comment");
    assert_eq!(
        region.text,
        " Crate-level documentation before malformed Rust source."
    );
    let owner = region
        .owner
        .as_ref()
        .expect("expected module owner metadata");
    assert_eq!(owner.kind, "module");
    assert!(owner.name.is_none());
    assert!(owner.qualname.is_none());
}

#[then("a recoverable Rust parse error is recorded")]
fn a_recoverable_rust_parse_error_is_recorded(rust_doc_comment_state: &RustDocCommentState) {
    let ir = extracted_ir(rust_doc_comment_state);

    assert!(!ir.errors.is_empty());
    assert!(
        ir.errors
            .iter()
            .any(|error| error.code == "rust-parse-recovery")
    );
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
