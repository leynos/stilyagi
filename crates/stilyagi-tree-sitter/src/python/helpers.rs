//! Helper functions for Python tree-sitter extraction.

use stilyagi_ir::{NodeFlags, SourceSpan};
use tree_sitter::Node;

use super::owner::{OwnerFrame, OwnerKind};
use super::types::{NodeId, NodeKind};

pub(super) fn nearest_emitted_owner(stack: &[OwnerFrame]) -> Option<NodeId> {
    stack
        .iter()
        .rev()
        .skip(1)
        .find_map(|frame| frame.emitted_node_id.clone())
}

pub(super) fn owner_frame_for_definition(
    source: &str,
    node: Node<'_>,
) -> Option<(OwnerKind, String)> {
    let kind = match node.kind() {
        "class_definition" => OwnerKind::Class,
        "function_definition" => OwnerKind::Function,
        _ => return None,
    };
    let name = node.child_by_field_name("name")?;
    Some((kind, text_for_node(source, name)?))
}

pub(super) fn module_docstring<'tree>(source: &str, root: Node<'tree>) -> Option<Node<'tree>> {
    let first = root.named_child(0)?;
    if let Some(docstring) = docstring_from_statement(source, first) {
        return Some(docstring);
    }
    if first.kind() == "ERROR" {
        // Malformed top-level syntax can wrap the leading docstring in ERROR;
        // recover one statement so broken code stays conservative.
        return first_statement_descendant(first)
            .and_then(|statement| docstring_from_statement(source, statement));
    }
    None
}

pub(super) fn definition_docstring<'tree>(source: &str, node: Node<'tree>) -> Option<Node<'tree>> {
    let body = node.child_by_field_name("body")?;
    docstring_from_statement(source, body.named_child(0)?)
}

fn docstring_from_statement<'tree>(source: &str, statement: Node<'tree>) -> Option<Node<'tree>> {
    if statement.kind() != "expression_statement" || statement.named_child_count() != 1 {
        return None;
    }
    let string = statement.named_child(0)?;
    is_plain_string_docstring(source, string).then_some(string)
}

fn first_statement_descendant(node: Node<'_>) -> Option<Node<'_>> {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if child.kind() == "expression_statement" {
            return Some(child);
        }
        if let Some(found) = first_statement_descendant(child) {
            return Some(found);
        }
    }
    None
}

/// Extract docstring text and source span from a Python string node.
/// Uses `string_content`, or delimiter spans when empty docstrings omit it.
pub(super) fn docstring_content(source: &str, string: Node<'_>) -> Option<(String, SourceSpan)> {
    if let Some(content) = direct_named_child_with_kind(string, NodeKind("string_content")) {
        return Some((text_for_node(source, content)?, source_span(content)));
    }
    let start = direct_named_child_with_kind(string, NodeKind("string_start"))?;
    let end = direct_named_child_with_kind(string, NodeKind("string_end"))?;
    let span = SourceSpan::new(start.end_byte(), end.start_byte())?;
    Some((String::new(), span))
}

/// Decide whether a first statement is a v1 Python docstring candidate.
/// V1 accepts only plain `string` nodes. Interpolations and `f`/`F` prefixes
/// are executable f-string content, while adjacent strings parse separately as
/// `concatenated_string`.
fn is_plain_string_docstring(source: &str, string: Node<'_>) -> bool {
    string.kind() == "string"
        && !has_descendant_kind(string, NodeKind("interpolation"))
        && !string_start_has_format_prefix(source, string)
}

fn string_start_has_format_prefix(source: &str, string: Node<'_>) -> bool {
    let Some(start) = direct_named_child_with_kind(string, NodeKind("string_start")) else {
        return false;
    };
    let Some(start_text) = text_for_node(source, start) else {
        return false;
    };
    start_text.to_ascii_lowercase().contains('f')
}

fn has_descendant_kind(node: Node<'_>, kind: NodeKind) -> bool {
    let mut cursor = node.walk();
    node.named_children(&mut cursor)
        .any(|child| child.kind() == kind.as_str() || has_descendant_kind(child, kind))
}

pub(super) fn collect_error_nodes<'tree>(node: Node<'tree>, errors: &mut Vec<Node<'tree>>) {
    if node.is_error() || node.is_missing() {
        errors.push(node);
    }
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        collect_error_nodes(child, errors);
    }
}

fn direct_named_child_with_kind(node: Node<'_>, kind: NodeKind) -> Option<Node<'_>> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor)
        .find(|child| child.kind() == kind.as_str())
}

pub(super) fn text_for_node(source: &str, node: Node<'_>) -> Option<String> {
    node.utf8_text(source.as_bytes()).ok().map(str::to_owned)
}

pub(super) fn source_span(node: Node<'_>) -> SourceSpan {
    let start = node.start_byte();
    let end = node.end_byte();
    // tree-sitter nodes guarantee ordered byte offsets. The fallback is only a
    // defensive guard against a future invariant break, preserving a bounded
    // source-backed span instead of panicking in extraction.
    SourceSpan::new(start, end).unwrap_or(SourceSpan {
        byte_start: start,
        byte_end: start,
    })
}

pub(super) fn node_flags(node: Node<'_>) -> NodeFlags {
    NodeFlags {
        named: node.is_named(),
        error: node.has_error() || node.is_error(),
        missing: node.is_missing(),
        synthetic: false,
    }
}
