//! Placeholder crate for tree-sitter-backed source extraction.

mod python;
mod rust;

pub use python::{PythonExtractError, python_docstring_ir_document};
pub use rust::{RustExtractError, rust_doc_comment_ir_document};

/// Marker type for the future tree-sitter extraction boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct TreeSitterBoundary;

#[cfg(test)]
mod tests {
    //! Tests for the placeholder tree-sitter extraction boundary marker.

    use super::TreeSitterBoundary;
    use crate::python::types::NodeKind;
    use stilyagi_test_fixtures::{
        MALFORMED_PYTHON_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH, read_corpus_fixture,
    };
    use tree_sitter::{Node, Parser};

    const SHARED_PYTHON_FIXTURE: &str = SHARED_PYTHON_FIXTURE_PATH;
    const MALFORMED_PYTHON_FIXTURE: &str = MALFORMED_PYTHON_FIXTURE_PATH;

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn tree_sitter_boundary_default_matches_the_marker_value() {
        assert_eq!(TreeSitterBoundary::default(), TreeSitterBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn tree_sitter_boundary_clone_matches_the_original() {
        let boundary = TreeSitterBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn tree_sitter_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{TreeSitterBoundary:?}").contains("TreeSitterBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn tree_sitter_boundary_is_copy() {
        let original = TreeSitterBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }

    fn python_parser() -> Parser {
        let mut parser = Parser::new();
        let language = tree_sitter_python::LANGUAGE.into();
        if let Err(error) = parser.set_language(&language) {
            panic!("tree-sitter-python grammar should load: {error}");
        }
        parser
    }

    fn parse_python(source: &str) -> tree_sitter::Tree {
        let Some(tree) = python_parser().parse(source, None) else {
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

    fn first_named_child_with_kind(node: Node<'_>, kind: NodeKind) -> Node<'_> {
        let child = first_named_child(node);

        assert_eq!(child.kind(), kind.as_str());
        child
    }

    fn direct_named_child_with_kind(node: Node<'_>, kind: NodeKind) -> Node<'_> {
        let mut cursor = node.walk();

        let Some(child) = node
            .named_children(&mut cursor)
            .find(|child| child.kind() == kind.as_str())
        else {
            panic!("{} child should exist", kind.as_str());
        };
        child
    }

    fn text_for_node<'source>(source: &'source str, node: Node<'_>) -> &'source str {
        match node.utf8_text(source.as_bytes()) {
            Ok(text) => text,
            Err(error) => panic!("node byte range should select valid UTF-8: {error}"),
        }
    }

    fn named_children_with_kind(node: Node<'_>, kind: NodeKind) -> Vec<Node<'_>> {
        let mut cursor = node.walk();

        node.named_children(&mut cursor)
            .filter(|child| child.kind() == kind.as_str())
            .collect()
    }

    fn descendants_with_kind(node: Node<'_>, kind: NodeKind) -> Vec<Node<'_>> {
        let mut found = Vec::new();
        collect_descendants_with_kind(node, kind, &mut found);
        found
    }

    fn collect_descendants_with_kind<'tree>(
        node: Node<'tree>,
        kind: NodeKind,
        found: &mut Vec<Node<'tree>>,
    ) {
        let mut cursor = node.walk();

        for child in node.named_children(&mut cursor) {
            if child.kind() == kind.as_str() {
                found.push(child);
            }
            collect_descendants_with_kind(child, kind, found);
        }
    }

    /// Pin the grammar shape used by the owner-aware extractor.
    #[test]
    fn python_fixture_exposes_docstring_content_spans() {
        let source = read_corpus_fixture(SHARED_PYTHON_FIXTURE)
            .expect("shared Python fixture should be readable");
        let tree = parse_python(&source);
        let root = tree.root_node();

        assert_eq!(root.kind(), "module");

        let expression_statement =
            first_named_child_with_kind(root, NodeKind("expression_statement"));
        let string = first_named_child_with_kind(expression_statement, NodeKind("string"));
        let string_content = direct_named_child_with_kind(string, NodeKind("string_content"));

        assert_eq!(
            text_for_node(&source, string_content),
            "Module docstring for the shared Stilyagi corpus."
        );
        assert_eq!(
            source
                .get(string_content.start_byte()..string_content.end_byte())
                .expect("string content span should be valid UTF-8"),
            "Module docstring for the shared Stilyagi corpus."
        );
    }

    /// Pin decorated definitions as transparent wrappers around their owners.
    #[test]
    fn python_fixture_reaches_staticmethod_definition_through_decorator() {
        let source = read_corpus_fixture(SHARED_PYTHON_FIXTURE)
            .expect("shared Python fixture should be readable");
        let tree = parse_python(&source);
        let decorated_definition =
            descendants_with_kind(tree.root_node(), NodeKind("decorated_definition"))
                .into_iter()
                .next()
                .expect("fixture should contain a decorated method");
        let definition = decorated_definition
            .child_by_field_name("definition")
            .expect("decorated definition should expose its inner definition");
        let name = definition
            .child_by_field_name("name")
            .expect("function definition should expose its name");

        assert_eq!(definition.kind(), "function_definition");
        assert_eq!(text_for_node(&source, name), "method");
    }

    /// Pin grammar signals used to reject v1 non-docstring first statements.
    #[test]
    fn python_grammar_marks_fstrings_and_concatenated_strings() {
        let f_string_source = "def interpolated():\n    f\"\"\"{value}\"\"\"\n";
        let f_string_tree = parse_python(f_string_source);
        let f_string = descendants_with_kind(f_string_tree.root_node(), NodeKind("string"))
            .into_iter()
            .next()
            .expect("f-string source should contain a string node");
        let string_start = first_named_child_with_kind(f_string, NodeKind("string_start"));

        assert!(
            descendants_with_kind(f_string, NodeKind("interpolation")).is_empty()
                || text_for_node(f_string_source, string_start).contains('f')
        );

        let concatenated_source = "def adjacent():\n    \"a\" \"b\"\n";
        let concatenated_tree = parse_python(concatenated_source);
        let first_statement = descendants_with_kind(
            concatenated_tree.root_node(),
            NodeKind("expression_statement"),
        )
        .into_iter()
        .next()
        .expect("concatenated source should contain an expression statement");
        let concatenated_string =
            first_named_child_with_kind(first_statement, NodeKind("concatenated_string"));

        assert_eq!(
            concatenated_string.kind(),
            NodeKind("concatenated_string").as_str()
        );
    }

    /// Pin malformed recovery so later extraction can safely emit partial IR.
    #[test]
    fn malformed_python_fixture_recovers_the_module_docstring() {
        let source = read_corpus_fixture(MALFORMED_PYTHON_FIXTURE)
            .expect("malformed Python fixture should be readable");
        let tree = parse_python(&source);
        let root = tree.root_node();
        let expression_statement = descendants_with_kind(root, NodeKind("expression_statement"))
            .into_iter()
            .next()
            .expect("malformed fixture should preserve an expression statement");
        let string = first_named_child_with_kind(expression_statement, NodeKind("string"));
        let string_content = direct_named_child_with_kind(string, NodeKind("string_content"));
        let error_nodes = descendants_with_kind(root, NodeKind("ERROR"));
        let error_spans = error_nodes
            .iter()
            .map(|node| (node.start_byte(), node.end_byte()))
            .collect::<Vec<_>>();
        let function_nodes = named_children_with_kind(root, NodeKind("function_definition"));

        assert!(root.has_error());
        assert_eq!(first_named_child(root).kind(), "ERROR");
        assert_eq!(
            text_for_node(&source, string_content),
            "Module docstring before malformed Python source."
        );
        assert_eq!(error_spans, vec![(0, 168), (57, 77)]);
        assert!(function_nodes.is_empty());
    }
}
