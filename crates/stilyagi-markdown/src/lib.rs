//! Markdown-specific extraction support.

use markdown::{ParseOptions, mdast::Node, message::Message, to_mdast};

/// Marker type for the future Markdown extraction boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct MarkdownBoundary;

/// Parse Markdown into an mdast tree using the workspace parser choice.
///
/// # Errors
///
/// Returns the parser's structured message when the input cannot be parsed
/// with the configured `markdown-rs` options.
pub fn parse_markdown_ast(source: &str) -> Result<Node, Message> {
    to_mdast(source, &ParseOptions::default())
}

#[cfg(test)]
mod tests {
    use markdown::mdast::Node;
    use rstest::rstest;

    use super::{MarkdownBoundary, parse_markdown_ast};

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn markdown_boundary_default_matches_the_marker_value() {
        assert_eq!(MarkdownBoundary::default(), MarkdownBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn markdown_boundary_clone_matches_the_original() {
        let boundary = MarkdownBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn markdown_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{MarkdownBoundary:?}").contains("MarkdownBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn markdown_boundary_is_copy() {
        let original = MarkdownBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }

    #[rstest]
    fn markdown_parser_reports_positions_for_representative_blocks() {
        let source = "# Heading\n\nA paragraph with [a link](https://example.com).\n";
        let tree = parse_markdown_ast(source);

        assert!(matches!(tree, Ok(Node::Root(_))));
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
}
