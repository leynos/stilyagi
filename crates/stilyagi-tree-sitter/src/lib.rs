//! Placeholder crate for tree-sitter-backed source extraction.

mod python;
mod rust;
#[cfg(test)]
mod test_support;

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
    use crate::test_support::{
        assert_first_named_child_kind, descendants_with_kind, direct_named_child_with_kind,
        first_named_child, named_children_with_kind, parse_python_source, text_for_node,
    };
    use stilyagi_test_fixtures::{
        MALFORMED_PYTHON_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH, read_corpus_fixture,
    };
    use tree_sitter::Node;

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

    /// Pin the grammar shape used by the owner-aware extractor.
    #[test]
    fn python_fixture_exposes_docstring_content_spans() {
        let source = read_corpus_fixture(SHARED_PYTHON_FIXTURE)
            .expect("shared Python fixture should be readable");
        let tree = parse_python_source(&source).expect("shared Python fixture should parse");
        let root = tree.root_node();

        assert_eq!(root.kind(), "module");

        let expression_statement =
            assert_first_named_child_kind!(root, NodeKind("expression_statement"));
        let string = assert_first_named_child_kind!(expression_statement, NodeKind("string"));
        let string_content = direct_named_child_with_kind(string, NodeKind("string_content"))
            .expect("string should expose a string_content child");
        let content_text = text_for_node(&source, string_content)
            .expect("string content should select valid UTF-8");

        assert_eq!(
            content_text,
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
        let tree = parse_python_source(&source).expect("shared Python fixture should parse");
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
        let name_text = text_for_node(&source, name).expect("name should select valid UTF-8");

        assert_eq!(definition.kind(), "function_definition");
        assert_eq!(name_text, "method");
    }

    /// Pin grammar signals used to reject v1 non-docstring first statements.
    #[test]
    fn python_grammar_marks_fstrings_and_concatenated_strings() {
        let f_string_source = "def interpolated():\n    f\"\"\"{value}\"\"\"\n";
        let f_string_tree = parse_python_source(f_string_source).expect("f-string source parses");
        let f_string = descendants_with_kind(f_string_tree.root_node(), NodeKind("string"))
            .into_iter()
            .next()
            .expect("f-string source should contain a string node");
        let string_start = assert_first_named_child_kind!(f_string, NodeKind("string_start"));
        let string_start_text = text_for_node(f_string_source, string_start)
            .expect("string start should select valid UTF-8");
        let interpolation_texts = node_texts(
            f_string_source,
            &descendants_with_kind(f_string, NodeKind("interpolation")),
        )
        .expect("interpolations should select valid UTF-8");

        // The grammar marks interpolation both by the `f` prefix on the string
        // start and by dedicated `interpolation` children, so v1 can reject
        // f-strings on either signal alone.
        assert_eq!(string_start_text, "f\"\"\"");
        assert_eq!(interpolation_texts, vec!["{value}"]);

        let concatenated_source = "def adjacent():\n    \"a\" \"b\"\n";
        let concatenated_tree =
            parse_python_source(concatenated_source).expect("concatenated source parses");
        let first_statement = descendants_with_kind(
            concatenated_tree.root_node(),
            NodeKind("expression_statement"),
        )
        .into_iter()
        .next()
        .expect("concatenated source should contain an expression statement");
        let concatenated_string =
            assert_first_named_child_kind!(first_statement, NodeKind("concatenated_string"));
        let concatenated_parts = node_texts(
            concatenated_source,
            &named_children_with_kind(concatenated_string, NodeKind("string")),
        )
        .expect("concatenated string parts should select valid UTF-8");

        // Adjacent literals stay separate `string` children, so the extractor
        // can see that the statement is not a single docstring literal.
        assert_eq!(concatenated_parts, vec!["\"a\"", "\"b\""]);
    }

    /// Return the source text of every node, or the first UTF-8 failure.
    fn node_texts<'source>(
        source: &'source str,
        nodes: &[Node<'_>],
    ) -> Result<Vec<&'source str>, std::str::Utf8Error> {
        nodes
            .iter()
            .map(|node| text_for_node(source, *node))
            .collect()
    }

    /// Pin malformed recovery so later extraction can safely emit partial IR.
    #[test]
    fn malformed_python_fixture_recovers_the_module_docstring() {
        let source = read_corpus_fixture(MALFORMED_PYTHON_FIXTURE)
            .expect("malformed Python fixture should be readable");
        let tree = parse_python_source(&source).expect("malformed Python fixture should parse");
        let root = tree.root_node();
        let expression_statement = descendants_with_kind(root, NodeKind("expression_statement"))
            .into_iter()
            .next()
            .expect("malformed fixture should preserve an expression statement");
        let string = assert_first_named_child_kind!(expression_statement, NodeKind("string"));
        let string_content = direct_named_child_with_kind(string, NodeKind("string_content"))
            .expect("string should expose a string_content child");
        let content_text = text_for_node(&source, string_content)
            .expect("string content should select valid UTF-8");
        let error_nodes = descendants_with_kind(root, NodeKind("ERROR"));
        let error_spans = error_nodes
            .iter()
            .map(|node| (node.start_byte(), node.end_byte()))
            .collect::<Vec<_>>();
        let function_nodes = named_children_with_kind(root, NodeKind("function_definition"));
        let first_child_kind = first_named_child(root)
            .expect("malformed fixture root should have a first named child")
            .kind();

        assert!(root.has_error());
        assert_eq!(first_child_kind, "ERROR");
        assert_eq!(
            content_text,
            "Module docstring before malformed Python source."
        );
        assert_eq!(error_spans, vec![(0, 168), (57, 77)]);
        assert!(function_nodes.is_empty());
    }
}
