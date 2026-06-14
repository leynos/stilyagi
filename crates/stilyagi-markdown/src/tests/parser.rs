//! Tests for Markdown AST parsing and panic containment.

use markdown::mdast::Node;
use rstest::rstest;

use crate::{parse_markdown_ast, parse_markdown_ast_with};

#[rstest]
fn markdown_parser_reports_positions_for_representative_blocks() {
    let source = "# Heading\n\nA paragraph with [a link](https://example.com).\n";
    let tree = parse_markdown_ast(source);

    assert!(matches!(&tree, Ok(Node::Root(_))));
    if let Ok(root) = tree {
        assert_node_start(&root, 0);
        assert_node_has_non_empty_span(&root);
        assert!(find_kind(&root, NodeKind::Heading).is_some());
        assert!(find_kind(&root, NodeKind::Paragraph).is_some());
        if let Some(heading) = find_kind(&root, NodeKind::Heading) {
            assert_node_start(heading, 0);
            assert_node_has_non_empty_span(heading);
        }
        if let Some(paragraph) = find_kind(&root, NodeKind::Paragraph) {
            assert_node_start(paragraph, 11);
            assert_node_has_non_empty_span(paragraph);
        }
    }
}

#[rstest]
fn markdown_parser_panics_are_contained_as_messages() {
    let result = parse_markdown_ast_with("content", |_| panic!("forced parser panic"));

    assert!(matches!(
        result,
        Err(ref error) if is_parser_panic_message(error)
    ));
}

fn is_parser_panic_message(error: &markdown::message::Message) -> bool {
    error.reason.contains("forced parser panic")
        && error.reason.contains("phase=parse")
        && error.reason.contains("path=<unknown>")
        && error.reason.contains("uri=<unknown>")
        && error.rule_id.as_ref() == "parser-panic"
        && error.source.as_ref() == "stilyagi-markdown"
}

#[derive(Clone, Copy)]
enum NodeKind {
    Heading,
    Paragraph,
}

fn find_kind(node: &Node, kind: NodeKind) -> Option<&Node> {
    if matches_kind(node, kind) {
        return Some(node);
    }
    if let Some(children) = node.children() {
        for child in children {
            if let Some(found) = find_kind(child, kind) {
                return Some(found);
            }
        }
    }
    None
}

fn matches_kind(node: &Node, kind: NodeKind) -> bool {
    matches!(
        (node, kind),
        (Node::Heading(_), NodeKind::Heading) | (Node::Paragraph(_), NodeKind::Paragraph)
    )
}

fn assert_node_start(node: &Node, start: usize) {
    let position = node.position();
    assert!(matches!(
        position,
        Some(value) if value.start.offset == start
    ));
}

fn assert_node_has_non_empty_span(node: &Node) {
    let position = node.position();
    assert!(matches!(
        position,
        Some(value) if value.start.offset < value.end.offset
    ));
}
