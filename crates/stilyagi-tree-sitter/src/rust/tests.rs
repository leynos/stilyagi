//! Tests for Rust doc-comment extraction.

use rstest::rstest;
use stilyagi_ir::SourceIdentity;
use stilyagi_test_fixtures::{
    ATTRIBUTE_RUST_FIXTURE_PATH, MALFORMED_RUST_FIXTURE_PATH, MULTILINE_RUST_FIXTURE_PATH,
    NESTED_RUST_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, read_corpus_fixture,
};
use tree_sitter::{Node, Parser};

use super::rust_doc_comment_ir_document;

const SHARED_RUST_FIXTURE: &str = SHARED_RUST_FIXTURE_PATH;
const ATTRIBUTE_RUST_FIXTURE: &str = ATTRIBUTE_RUST_FIXTURE_PATH;
const MALFORMED_RUST_FIXTURE: &str = MALFORMED_RUST_FIXTURE_PATH;
const NESTED_RUST_FIXTURE: &str = NESTED_RUST_FIXTURE_PATH;
const MULTILINE_RUST_FIXTURE: &str = MULTILINE_RUST_FIXTURE_PATH;

fn extract_rust(source: &str) -> stilyagi_ir::IrDocument {
    match rust_doc_comment_ir_document(source, SourceIdentity::anonymous()) {
        Ok(document) => document,
        Err(error) => panic!("expected Rust extraction: {error:?}"),
    }
}

fn fixture_document(path: &str) -> stilyagi_ir::IrDocument {
    let source: String = match read_corpus_fixture(path) {
        Ok(source) => source,
        Err(error) => panic!("expected Rust fixture {path}: {error}"),
    };

    extract_rust(&source)
}

fn rust_parser() -> Parser {
    let mut parser = Parser::new();
    let language = tree_sitter_rust::LANGUAGE.into();
    if let Err(error) = parser.set_language(&language) {
        panic!("tree-sitter-rust grammar should load: {error}");
    }
    parser
}

fn parse_rust(source: &str) -> tree_sitter::Tree {
    let Some(tree) = rust_parser().parse(source, None) else {
        panic!("tree-sitter should return a parse tree");
    };
    tree
}

fn first_named_child(node: Node<'_>) -> Node<'_> {
    let Some(child) = node.named_child(0) else {
        panic!("node should have a first named child");
    };
    child
}

fn first_named_child_with_kind<'a>(node: Node<'a>, kind: &str) -> Node<'a> {
    let child = first_named_child(node);
    assert_eq!(child.kind(), kind);
    child
}

fn direct_named_child_with_kind<'a>(node: Node<'a>, kind: &str) -> Node<'a> {
    let mut cursor = node.walk();
    let Some(child) = node
        .named_children(&mut cursor)
        .find(|child| child.kind() == kind)
    else {
        panic!("expected {kind} child");
    };
    child
}

fn text_for_node<'a>(source: &'a str, node: Node<'a>) -> &'a str {
    match node.utf8_text(source.as_bytes()) {
        Ok(text) => text,
        Err(error) => panic!("node byte range should select valid UTF-8: {error}"),
    }
}

fn descendants_with_kind<'a>(node: Node<'a>, kind: &str) -> Vec<Node<'a>> {
    let mut found = Vec::new();
    collect_descendants_with_kind(node, kind, &mut found);
    found
}

fn collect_descendants_with_kind<'tree>(
    node: Node<'tree>,
    kind: &str,
    found: &mut Vec<Node<'tree>>,
) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == kind {
            found.push(child);
        }
        collect_descendants_with_kind(child, kind, found);
    }
}

#[rstest]
fn shared_fixture_exposes_doc_comment_nodes_and_siblings() {
    let source =
        read_corpus_fixture(SHARED_RUST_FIXTURE).expect("shared Rust fixture should be readable");
    let tree = parse_rust(&source);
    let root = tree.root_node();

    assert_eq!(root.kind(), "source_file");

    let crate_comment = first_named_child_with_kind(root, "line_comment");
    assert!(text_for_node(&source, crate_comment).starts_with("//!"));
    assert_eq!(
        text_for_node(&source, crate_comment)
            .strip_prefix("//!")
            .expect("crate doc should use the inner doc marker")
            .trim_end_matches(['\r', '\n']),
        " Crate-level documentation comment for the shared Stilyagi corpus."
    );

    let struct_comment = descendants_with_kind(root, "line_comment")
        .into_iter()
        .find(|node| text_for_node(&source, *node).starts_with("/// Item-level"))
        .expect("expected struct doc comment");
    let struct_item = struct_comment
        .next_named_sibling()
        .expect("struct doc comment should have a sibling item");
    assert_eq!(struct_item.kind(), "struct_item");
    let struct_name = struct_item
        .child_by_field_name("name")
        .expect("struct item should expose its name field");
    assert_eq!(text_for_node(&source, struct_name), "FixtureExample");

    let impl_item = direct_named_child_with_kind(root, "impl_item");
    let method_comment = descendants_with_kind(impl_item, "line_comment")
        .into_iter()
        .find(|node| text_for_node(&source, *node).starts_with("/// Method"))
        .expect("expected method doc comment");
    let method_item = method_comment
        .next_named_sibling()
        .expect("method doc comment should have a sibling item");
    assert_eq!(method_item.kind(), "function_item");
    let method_name = method_item
        .child_by_field_name("name")
        .expect("function item should expose its name field");
    assert_eq!(text_for_node(&source, method_name), "documented_value");

    let suppressed_comment = descendants_with_kind(root, "line_comment")
        .into_iter()
        .find(|node| text_for_node(&source, *node).starts_with("// stilyagi-disable-next-line"))
        .expect("expected suppression marker");
    assert!(text_for_node(&source, suppressed_comment).starts_with("//"));
    assert!(!text_for_node(&source, suppressed_comment).starts_with("///"));
}

#[rstest]
fn attribute_fixture_carries_doc_comments_across_attributes() {
    let document = fixture_document(ATTRIBUTE_RUST_FIXTURE);
    let kinds = document
        .nodes
        .iter()
        .map(|node| node.kind.as_str())
        .collect::<Vec<_>>();

    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        document
            .regions
            .first()
            .expect("expected attribute fixture doc-comment")
            .owner
            .as_ref()
            .map(|owner| (
                owner.kind.as_str(),
                owner.name.as_deref(),
                owner.qualname.as_deref()
            )),
        Some((
            "struct",
            Some("AttributeFixture"),
            Some("attribute_fixture::AttributeFixture"),
        ))
    );
    assert_eq!(
        document
            .regions
            .first()
            .expect("expected attribute fixture doc-comment")
            .text,
        " Documentation comment that must attach to the struct, not the derive."
    );
    assert!(!kinds.contains(&"attribute_item"));
    assert!(!kinds.contains(&"inner_attribute_item"));
}

#[rstest]
fn block_doc_comment_classification_edge_rules() {
    let struct_source = "/** outer */ struct S;";
    let struct_tree = parse_rust(struct_source);
    let struct_root = struct_tree.root_node();
    let struct_comment = first_named_child_with_kind(struct_root, "block_comment");
    assert!(text_for_node(struct_source, struct_comment).starts_with("/**"));
    let struct_region = extract_rust(struct_source)
        .regions
        .into_iter()
        .next()
        .expect("expected one extracted region");
    assert_eq!(struct_region.kind, "rust_doc_comment");
    assert_eq!(struct_region.text, " outer ");

    let inner_source = "/*! inner */";
    let inner_tree = parse_rust(inner_source);
    let inner_root = inner_tree.root_node();
    let inner_comment = first_named_child_with_kind(inner_root, "block_comment");
    assert!(text_for_node(inner_source, inner_comment).starts_with("/*!"));
    let inner_region = extract_rust(inner_source)
        .regions
        .into_iter()
        .next()
        .expect("expected one extracted region");
    assert_eq!(inner_region.text, " inner ");
}

#[rstest]
#[case("////")]
#[case("/**/")]
#[case("/***/")]
fn non_doc_comment_edge_cases_emit_no_regions(#[case] source: &str) {
    let tree = parse_rust(source);
    let root = tree.root_node();
    let comment = first_named_child(root);

    assert!(text_for_node(source, comment).starts_with('/'));
    assert!(extract_rust(source).regions.is_empty());
}

#[rstest]
fn multiline_fixture_merges_three_line_comments_and_block_comment() {
    let document = fixture_document(MULTILINE_RUST_FIXTURE);
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
    let document = fixture_document(NESTED_RUST_FIXTURE);
    let owners = document
        .regions
        .iter()
        .map(|region| {
            let owner = region.owner.as_ref().expect("expected owner metadata");
            (
                region.text.as_str(),
                owner.kind.as_str(),
                owner.name.as_deref(),
                owner.qualname.as_deref(),
            )
        })
        .collect::<Vec<_>>();

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
        Some("FixtureExample::VALUE"),
    )));
    assert!(owners.contains(&(
        " Documented associated type in a trait impl.",
        "type",
        Some("Alias"),
        Some("FixtureExample::Alias"),
    )));
    assert!(owners.contains(&(
        " Documented method in a trait impl.",
        "function",
        Some("documented_value"),
        Some("FixtureExample::documented_value"),
    )));
}

#[rstest]
fn malformed_fixture_yields_partial_ir_and_errors() {
    let document = fixture_document(MALFORMED_RUST_FIXTURE);
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
    let document = extract_rust(source);
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
