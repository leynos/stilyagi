//! Tests for Rust doc-comment extraction.

use rstest::rstest;
use stilyagi_test_fixtures::{
    ATTRIBUTE_RUST_FIXTURE_PATH, MALFORMED_RUST_FIXTURE_PATH, MULTILINE_RUST_FIXTURE_PATH,
    NESTED_RUST_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, read_corpus_fixture,
};
use tree_sitter::Node;

use crate::test_support::{
    assert_first_named_child_kind, descendants_with_kind, direct_named_child_with_kind,
    extract_rust, first_named_child, owner_triple, parse_rust_source, region_owners,
    rust_fixture_document, text_for_node,
};

const SHARED_RUST_FIXTURE: &str = SHARED_RUST_FIXTURE_PATH;
const ATTRIBUTE_RUST_FIXTURE: &str = ATTRIBUTE_RUST_FIXTURE_PATH;
const MALFORMED_RUST_FIXTURE: &str = MALFORMED_RUST_FIXTURE_PATH;
const NESTED_RUST_FIXTURE: &str = NESTED_RUST_FIXTURE_PATH;
const MULTILINE_RUST_FIXTURE: &str = MULTILINE_RUST_FIXTURE_PATH;

/// Return the first `line_comment` descendant whose text starts with `prefix`.
fn line_comment_starting_with<'tree>(
    source: &str,
    node: Node<'tree>,
    prefix: &str,
) -> Option<Node<'tree>> {
    descendants_with_kind(node, "line_comment")
        .into_iter()
        .find(|comment| text_for_node(source, *comment).is_ok_and(|text| text.starts_with(prefix)))
}

/// Return the item documented by the first line comment matching `prefix`.
fn documented_item<'tree>(source: &str, node: Node<'tree>, prefix: &str) -> Option<Node<'tree>> {
    line_comment_starting_with(source, node, prefix)?.next_named_sibling()
}

/// Return the text of an item's `name` field.
fn name_text<'source>(source: &'source str, item: Node<'_>) -> Option<&'source str> {
    let name = item.child_by_field_name("name")?;

    text_for_node(source, name).ok()
}

#[rstest]
fn shared_fixture_exposes_doc_comment_nodes_and_siblings() {
    let source =
        read_corpus_fixture(SHARED_RUST_FIXTURE).expect("shared Rust fixture should be readable");
    let tree = parse_rust_source(&source).expect("shared Rust fixture should parse");
    let root = tree.root_node();
    let crate_comment = assert_first_named_child_kind!(root, "line_comment");
    let crate_comment_text =
        text_for_node(&source, crate_comment).expect("crate doc comment should be valid UTF-8");
    let struct_item = documented_item(&source, root, "/// Item-level")
        .expect("struct doc comment should have a sibling item");
    let struct_name =
        name_text(&source, struct_item).expect("struct item should expose its name field");
    let impl_item =
        direct_named_child_with_kind(root, "impl_item").expect("fixture should contain an impl");
    let method_item = documented_item(&source, impl_item, "/// Method")
        .expect("method doc comment should have a sibling item");
    let method_name =
        name_text(&source, method_item).expect("function item should expose its name field");
    let suppressed_comment = line_comment_starting_with(&source, root, "// stilyagi: ignore-next")
        .expect("expected suppression marker");
    let suppressed_text = text_for_node(&source, suppressed_comment)
        .expect("suppression marker should be valid UTF-8");

    assert_eq!(root.kind(), "source_file");
    assert!(crate_comment_text.starts_with("//!"));
    assert_eq!(
        crate_comment_text
            .strip_prefix("//!")
            .expect("crate doc should use the inner doc marker")
            .trim_end_matches(['\r', '\n']),
        " Crate-level documentation comment for the shared Stilyagi corpus."
    );
    assert_eq!(struct_item.kind(), "struct_item");
    assert_eq!(struct_name, "FixtureExample");
    assert_eq!(method_item.kind(), "function_item");
    assert_eq!(method_name, "documented_value");
    assert!(suppressed_text.starts_with("//"));
    assert!(!suppressed_text.starts_with("///"));
}

#[rstest]
fn attribute_fixture_carries_doc_comments_across_attributes() {
    let document =
        rust_fixture_document(ATTRIBUTE_RUST_FIXTURE).expect("expected attribute fixture IR");
    let kinds = document
        .nodes
        .iter()
        .map(|node| node.kind.as_str())
        .collect::<Vec<_>>();
    let region = document
        .regions
        .first()
        .expect("expected attribute fixture doc-comment");

    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        owner_triple(region),
        Some((
            "struct",
            Some("AttributeFixture"),
            Some("attribute_fixture::AttributeFixture"),
        ))
    );
    assert_eq!(
        region.text,
        " Documentation comment that must attach to the struct, not the derive."
    );
    assert!(!kinds.contains(&"attribute_item"));
    assert!(!kinds.contains(&"inner_attribute_item"));
}

#[rstest]
fn block_doc_comment_classification_edge_rules() {
    let struct_source = "/** outer */ struct S;";
    let struct_tree = parse_rust_source(struct_source).expect("outer block doc source parses");
    let struct_root = struct_tree.root_node();
    let struct_comment = assert_first_named_child_kind!(struct_root, "block_comment");
    let struct_comment_text =
        text_for_node(struct_source, struct_comment).expect("block comment should be valid UTF-8");
    let struct_region = extract_rust(struct_source)
        .expect("expected Rust extraction")
        .regions
        .into_iter()
        .next()
        .expect("expected one extracted region");

    assert!(struct_comment_text.starts_with("/**"));
    assert_eq!(struct_region.kind, "rust_doc_comment");
    assert_eq!(struct_region.text, " outer ");

    let inner_source = "/*! inner */";
    let inner_tree = parse_rust_source(inner_source).expect("inner block doc source parses");
    let inner_root = inner_tree.root_node();
    let inner_comment = assert_first_named_child_kind!(inner_root, "block_comment");
    let inner_comment_text =
        text_for_node(inner_source, inner_comment).expect("block comment should be valid UTF-8");
    let inner_region = extract_rust(inner_source)
        .expect("expected Rust extraction")
        .regions
        .into_iter()
        .next()
        .expect("expected one extracted region");

    assert!(inner_comment_text.starts_with("/*!"));
    assert_eq!(inner_region.text, " inner ");
}

#[rstest]
#[case("////")]
#[case("/**/")]
#[case("/***/")]
fn non_doc_comment_edge_cases_emit_no_regions(#[case] source: &str) {
    let tree = parse_rust_source(source).expect("non-doc comment source should parse");
    let root = tree.root_node();
    let comment = first_named_child(root).expect("source should have a first named child");
    let comment_text = text_for_node(source, comment).expect("comment should be valid UTF-8");
    let document = extract_rust(source).expect("expected Rust extraction");

    assert!(comment_text.starts_with('/'));
    assert!(document.regions.is_empty());
}

#[rstest]
fn multiline_fixture_merges_three_line_comments_and_block_comment() {
    let document =
        rust_fixture_document(MULTILINE_RUST_FIXTURE).expect("expected multiline fixture IR");
    let Some(first_region) = document.regions.first() else {
        panic!("expected first Rust doc-comment region");
    };
    let Some(second_region) = document.regions.get(1) else {
        panic!("expected second Rust doc-comment region");
    };

    assert_eq!(document.regions.len(), 2);
    assert_eq!(
        first_region.text,
        " First line of a multiline Rust doc comment.  Second line keeps the same owner.  Third line completes the merged region."
    );
    assert!(first_region.segments_reconstruct_text());
    assert_eq!(
        first_region.owner.as_ref().map(|owner| owner.kind.as_str()),
        Some("struct")
    );
    assert_eq!(second_region.text, " Block doc comment on one line. ");
    assert!(second_region.segments_reconstruct_text());
    assert_eq!(
        second_region
            .owner
            .as_ref()
            .map(|owner| owner.kind.as_str()),
        Some("function")
    );
}

#[rstest]
fn nested_fixture_uses_rust_qualname_semantics() {
    let document = rust_fixture_document(NESTED_RUST_FIXTURE).expect("expected nested fixture IR");
    let owners = region_owners(&document).expect("expected owner metadata");

    assert!(owners.contains(&(
        " Outer module documentation comment for nested Rust extraction.",
        "module",
        Some("outer"),
        Some("outer"),
    )));
    assert!(owners.contains(&(
        " Inner module documentation comment for the outer module.",
        "module",
        Some("outer"),
        Some("outer"),
    )));
    assert!(owners.contains(&(
        " Documented struct in a nested module.",
        "struct",
        Some("FixtureExample"),
        Some("outer::inner::FixtureExample"),
    )));
    assert!(owners.contains(&(
        " Documented associated const in a trait impl.",
        "const",
        Some("VALUE"),
        Some("outer::inner::FixtureExample::VALUE"),
    )));
    assert!(owners.contains(&(
        " Documented associated type in a trait impl.",
        "type",
        Some("Alias"),
        Some("outer::inner::FixtureExample::Alias"),
    )));
    assert!(owners.contains(&(
        " Documented method in a trait impl.",
        "function",
        Some("documented_value"),
        Some("outer::inner::FixtureExample::documented_value"),
    )));
}

#[rstest]
fn malformed_fixture_yields_partial_ir_and_errors() {
    let document =
        rust_fixture_document(MALFORMED_RUST_FIXTURE).expect("expected malformed fixture IR");
    let Some(region) = document.regions.first() else {
        panic!("expected malformed Rust fixture to yield one region");
    };

    assert!(!document.errors.is_empty());
    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "rust-parse-recovery")
    );
    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        region.text,
        " Crate-level documentation before malformed Rust source."
    );
}

#[rstest]
fn recovery_preserves_prefix_docs_and_reports_parse_errors() {
    let source = r#"//! Crate docs before malformed Rust source.

/// Broken function docs.
pub fn broken_function() {
    let value = "unterminated block";

/// Later struct docs.
pub struct Later;
"#;
    let document = extract_rust(source).expect("expected Rust extraction");
    let texts = document
        .regions
        .iter()
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>();

    assert!(texts.contains(&" Crate docs before malformed Rust source."));
    assert_eq!(
        texts,
        vec![
            " Crate docs before malformed Rust source.",
            " Later struct docs.",
        ]
    );
    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "rust-parse-recovery")
    );
}
