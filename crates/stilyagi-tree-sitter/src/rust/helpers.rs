//! Helper functions for Rust tree-sitter extraction.

use stilyagi_ir::{NodeFlags, SourceSpan};
use tree_sitter::Node;

use super::owner::{OwnerFrame, OwnerKind};
use super::types::NodeId;

/// Rust documentation-comment flavour derived from leading source bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum DocCommentFlavor {
    OuterLine,
    InnerLine,
    OuterBlock,
    InnerBlock,
}

impl DocCommentFlavor {
    /// Return whether this flavour is a line comment.
    pub(super) const fn is_line(self) -> bool {
        matches!(self, Self::OuterLine | Self::InnerLine)
    }

    /// Return whether this flavour is inner documentation.
    pub(super) const fn is_inner(self) -> bool {
        matches!(self, Self::InnerLine | Self::InnerBlock)
    }
}

/// Classify a comment node into a Rust documentation-comment flavour.
pub(super) fn classify_doc_comment(source: &str, node: Node<'_>) -> Option<DocCommentFlavor> {
    let text = source.get(node.start_byte()..node.end_byte())?;
    if let Some(rest) = text.strip_prefix("///") {
        return (!rest.starts_with('/')).then_some(DocCommentFlavor::OuterLine);
    }
    if text.starts_with("//!") {
        return Some(DocCommentFlavor::InnerLine);
    }
    if let Some(rest) = text.strip_prefix("/**") {
        return (!matches!(rest.chars().next(), Some('*' | '/')))
            .then_some(DocCommentFlavor::OuterBlock);
    }
    text.strip_prefix("/*!")
        .map(|_| DocCommentFlavor::InnerBlock)
}

/// Return the content span for a documentation comment.
pub(super) fn doc_comment_content_span(
    source: &str,
    node: Node<'_>,
    flavor: DocCommentFlavor,
) -> Option<SourceSpan> {
    let start = node.start_byte();
    let end = node.end_byte();
    match flavor {
        DocCommentFlavor::OuterLine | DocCommentFlavor::InnerLine => {
            SourceSpan::new(start + 3, line_comment_content_end(source, node))
        }
        DocCommentFlavor::OuterBlock | DocCommentFlavor::InnerBlock => {
            let content = source.get(start..end)?;
            let content_end = content.len().saturating_sub(2);
            SourceSpan::new(start + 3, start + content_end)
        }
    }
}

/// Return the source text covered by a node.
pub(super) fn text_for_node(source: &str, node: Node<'_>) -> Option<String> {
    node.utf8_text(source.as_bytes()).ok().map(str::to_owned)
}

/// Return the source text for a tree-sitter child field when present.
pub(super) fn text_for_field(source: &str, node: Node<'_>, field: &str) -> Option<String> {
    node.child_by_field_name(field)
        .and_then(|child| text_for_node(source, child))
}

/// Return the source span covered by a node.
pub(super) fn source_span(node: Node<'_>) -> SourceSpan {
    let start = node.start_byte();
    let end = node.end_byte();
    SourceSpan::new(start, end).unwrap_or(SourceSpan {
        byte_start: start,
        byte_end: start,
    })
}

/// Return node flags derived from tree-sitter metadata.
pub(super) fn node_flags(node: Node<'_>) -> NodeFlags {
    NodeFlags {
        named: node.is_named(),
        error: node.has_error() || node.is_error(),
        missing: node.is_missing(),
        synthetic: false,
    }
}

/// Return the owner-frame kind and name for a Rust item node.
pub(super) fn owner_frame_for_item(source: &str, node: Node<'_>) -> Option<OwnerFrame> {
    let kind = match node.kind() {
        "mod_item" => OwnerKind::Module,
        "impl_item" => OwnerKind::Impl,
        "struct_item" => OwnerKind::Struct,
        "enum_item" => OwnerKind::Enum,
        "union_item" => OwnerKind::Union,
        "trait_item" => OwnerKind::Trait,
        "function_item" => OwnerKind::Function,
        "const_item" => OwnerKind::Const,
        "static_item" => OwnerKind::Static,
        "type_item" => OwnerKind::Type,
        "macro_definition" => OwnerKind::Macro,
        "attribute_item" | "inner_attribute_item" => return None,
        kind if kind.ends_with("_item") => OwnerKind::Item,
        _ => return None,
    };
    Some(OwnerFrame::new(kind, owner_name(source, node)))
}

/// Return the parsed owner name for an item node when available.
pub(super) fn owner_name(source: &str, node: Node<'_>) -> Option<String> {
    match node.kind() {
        "impl_item" => text_for_field(source, node, "type")
            .or_else(|| text_for_field(source, node, "self_type")),
        _ => text_for_field(source, node, "name"),
    }
}

/// Return the body node for a Rust owner-bearing item, if one exists.
pub(super) fn item_body(node: Node<'_>) -> Option<Node<'_>> {
    node.child_by_field_name("body")
}

/// Return whether a module item starts with inner doc comments.
pub(super) fn module_body_has_leading_inner_docs(source: &str, node: Node<'_>) -> bool {
    let Some(body) = item_body(node) else {
        return false;
    };

    let mut cursor = body.walk();
    for child in body.named_children(&mut cursor) {
        if matches!(
            child.kind(),
            "attribute_item" | "inner_attribute_item" | "line_comment" | "block_comment"
        ) {
            continue;
        }
        return classify_doc_comment(source, child).is_some_and(DocCommentFlavor::is_inner);
    }

    false
}

/// Return whether two line comments can merge without a blank-line gap.
pub(super) fn line_comments_can_merge(
    source: &str,
    previous_end: usize,
    next_start: usize,
) -> bool {
    let gap = source.get(previous_end..next_start).unwrap_or("");
    gap.bytes().filter(|byte| *byte == b'\n').count() == 1
}

/// Return the end of a line comment's content, excluding the line ending.
pub(super) fn line_comment_content_end(source: &str, node: Node<'_>) -> usize {
    let end = node.end_byte();
    let bytes = source.as_bytes();
    if end >= 2 && bytes.get(end - 2..end) == Some(b"\r\n") {
        end - 2
    } else if end >= 1 && bytes.get(end - 1) == Some(&b'\n') {
        end - 1
    } else {
        end
    }
}

/// Return whether a node should be counted as a recovery anomaly.
pub(super) fn is_recovery_node(node: Node<'_>) -> bool {
    node.is_error() || node.is_missing()
}

/// Collect top-level recovery nodes in source order without descending into
/// broken subtrees.
pub(super) fn collect_recovery_nodes<'tree>(node: Node<'tree>, errors: &mut Vec<Node<'tree>>) {
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        if current.is_error() || current.is_missing() {
            errors.push(current);
            continue;
        }
        let mut cursor = current.walk();
        let mut children = current.children(&mut cursor).collect::<Vec<_>>();
        children.reverse();
        pending.extend(children);
    }
}

/// Collect documentation comments beneath a node, including descendants of
/// recovered subtrees.
pub(super) fn collect_doc_comment_nodes<'tree>(
    source: &str,
    node: Node<'tree>,
    comments: &mut Vec<Node<'tree>>,
) {
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        if classify_doc_comment(source, child).is_some() {
            comments.push(child);
        }
        collect_doc_comment_nodes(source, child, comments);
    }
}

/// Return the nearest emitted owner node id up the stack.
pub(super) fn nearest_emitted_owner(stack: &[OwnerFrame]) -> Option<NodeId> {
    stack
        .iter()
        .rev()
        .skip(1)
        .find_map(|frame| frame.emitted_node_id.clone())
}

/// Return the current emitted owner node id, defaulting to the crate root.
pub(super) fn current_owner_node_id(stack: &[OwnerFrame]) -> NodeId {
    nearest_emitted_owner(stack).unwrap_or_else(root_node_id)
}

/// Return the stable root node identifier.
pub(super) fn root_node_id() -> NodeId {
    NodeId("n0".to_owned())
}
