//! Scope and attribute helpers for Markdown region emission.
//!
//! These free functions translate AST node details and the enclosing list
//! context into the scope tags and attributes carried by emitted regions.

use std::collections::BTreeMap;

use markdown::mdast::Node;
use stilyagi_ir::SourceSpan;

use crate::builder::ListContext;

/// Builds the scope for a list item, recording whether its list is ordered
/// and whether the item is a task.
pub(super) fn list_item_scope(
    kind: &str,
    list_item: &markdown::mdast::ListItem,
    list_context: Option<&ListContext>,
) -> Vec<String> {
    let mut scope = vec!["markdown".to_owned(), kind.to_owned()];
    let list_kind = if list_context.is_some_and(|context| context.ordered) {
        "ordered"
    } else {
        "unordered"
    };
    scope.push(list_kind.to_owned());
    if list_item.checked.is_some() {
        scope.push("task".to_owned());
    }
    scope
}

/// Builds the attributes for a list item: ordering, spread, optional start
/// index, and checked state for task items.
pub(super) fn list_item_attrs(
    list_item: &markdown::mdast::ListItem,
    list_context: Option<&ListContext>,
) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    let ordered = list_context.is_some_and(|context| context.ordered);
    attrs.insert("ordered".to_owned(), serde_json::json!(ordered));
    attrs.insert("spread".to_owned(), serde_json::json!(list_item.spread));
    if let Some(start) = list_context.and_then(|context| context.start) {
        attrs.insert("start".to_owned(), serde_json::json!(start));
    }
    if let Some(checked) = list_item.checked {
        attrs.insert("checked".to_owned(), serde_json::json!(checked));
    }
    attrs
}

/// Builds the scope for a blockquote, encoding its nesting depth as `depthN`.
pub(super) fn blockquote_scope(kind: &str, depth: usize) -> Vec<String> {
    vec![
        "markdown".to_owned(),
        kind.to_owned(),
        format!("depth{depth}"),
    ]
}

/// Builds the attributes for a blockquote, recording its nesting depth.
pub(super) fn blockquote_attrs(depth: usize) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("depth".to_owned(), serde_json::json!(depth));
    attrs
}

/// Builds the attributes for an image region: URL, title, and a
/// `source_backed` flag of `false` because the alt text is decoded.
pub(super) fn image_attrs(image: &markdown::mdast::Image) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("url".to_owned(), serde_json::json!(image.url));
    attrs.insert("source_backed".to_owned(), serde_json::json!(false));
    if let Some(title) = image.title.as_ref() {
        attrs.insert("title".to_owned(), serde_json::json!(title));
    }
    attrs
}

/// Builds the attributes for a link title region: URL, title, and a
/// `source_backed` flag of `false` because the title is decoded.
pub(super) fn link_attrs(link: &markdown::mdast::Link) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("url".to_owned(), serde_json::json!(link.url));
    attrs.insert("source_backed".to_owned(), serde_json::json!(false));
    if let Some(title) = link.title.as_ref() {
        attrs.insert("title".to_owned(), serde_json::json!(title));
    }
    attrs
}

/// Returns the span of a positioned node, or `None` when it is unusable.
pub(super) fn span_from_positioned_node(node: &Node) -> Option<SourceSpan> {
    let position = node.position()?;
    SourceSpan::new(position.start.offset, position.end.offset)
}
