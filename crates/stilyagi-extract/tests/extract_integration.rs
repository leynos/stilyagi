//! Integration tests for `stilyagi-extract`.

#[path = "extract/extraction_behaviour.rs"]
mod extraction_behaviour;
#[path = "extract/fixture_path_validation.rs"]
mod fixture_path_validation;
#[path = "extract/ir_identity.rs"]
mod ir_identity;
#[path = "extract/markdown_suppression_bdd.rs"]
mod markdown_suppression_bdd;
#[path = "extract/python_docstring_bdd.rs"]
mod python_docstring_bdd;
#[path = "extract/region_vocabulary.rs"]
mod region_vocabulary;
#[path = "extract/rust_doc_comment_bdd.rs"]
mod rust_doc_comment_bdd;
#[path = "extract/spelling_display.rs"]
mod spelling_display;

#[path = "extract/test_utils.rs"]
mod test_utils;
