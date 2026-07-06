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
    let mut pending = node.named_children(&mut cursor).collect::<Vec<_>>();
    pending.reverse();
    while let Some(current) = pending.pop() {
        if current.kind() == "expression_statement" {
            return Some(current);
        }
        let mut current_cursor = current.walk();
        let mut children = current
            .named_children(&mut current_cursor)
            .collect::<Vec<_>>();
        children.reverse();
        pending.extend(children);
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
/// are executable f-string content, `b`/`B` prefixes are byte-string literals
/// (which Python never treats as docstrings), and adjacent strings parse
/// separately as `concatenated_string`.
fn is_plain_string_docstring(source: &str, string: Node<'_>) -> bool {
    string.kind() == "string"
        && !has_descendant_kind(string, NodeKind("interpolation"))
        && !string_start_has_disallowed_prefix(source, string)
}

/// Detect string-start prefixes that disqualify a literal from being a v1
/// docstring: `f`/`F` (f-strings) and `b`/`B` (byte strings, including combined
/// forms such as `rb`/`br`). Raw (`r`/`R`) and unicode (`u`/`U`) prefixes are
/// left as plain docstrings.
fn string_start_has_disallowed_prefix(source: &str, string: Node<'_>) -> bool {
    let Some(start) = direct_named_child_with_kind(string, NodeKind("string_start")) else {
        return false;
    };
    let Some(start_text) = text_for_node(source, start) else {
        return false;
    };
    let prefix = start_text.to_ascii_lowercase();
    prefix.contains('f') || prefix.contains('b')
}

fn has_descendant_kind(node: Node<'_>, kind: NodeKind) -> bool {
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        let mut cursor = current.walk();
        for child in current.named_children(&mut cursor) {
            if child.kind() == kind.as_str() {
                return true;
            }
            pending.push(child);
        }
    }
    false
}

pub(super) fn collect_error_nodes<'tree>(node: Node<'tree>, errors: &mut Vec<Node<'tree>>) {
    // Iterative pre-order walk over an explicit stack so deeply nested or
    // adversarial malformed files cannot overflow the call stack. Children are
    // reversed onto the stack so the leftmost is visited first, preserving the
    // document-order collection that a recursive descent would produce.
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        if current.is_error() || current.is_missing() {
            errors.push(current);
        }
        let mut cursor = current.walk();
        let mut children: Vec<Node<'tree>> = current.children(&mut cursor).collect();
        children.reverse();
        pending.extend(children);
    }
}

/// Collect comment nodes beneath a node, including descendants of recovered
/// subtrees.
pub(super) fn collect_comment_nodes<'tree>(node: Node<'tree>, comments: &mut Vec<Node<'tree>>) {
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        if current.kind() == "comment" {
            comments.push(current);
        }
        let mut cursor = current.walk();
        let mut children: Vec<Node<'tree>> = current.children(&mut cursor).collect();
        children.reverse();
        pending.extend(children);
    }
}

/// Return a Python comment body with the leading `#` removed.
pub(super) fn comment_body(source: &str, comment: Node<'_>) -> Option<String> {
    text_for_node(source, comment)?
        .strip_prefix('#')
        .map(ToOwned::to_owned)
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
