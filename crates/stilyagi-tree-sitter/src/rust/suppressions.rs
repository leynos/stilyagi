//! Comment-based suppression extraction for Rust sources.

use std::collections::BTreeMap;

use stilyagi_ir::suppression::{SuppressionCandidate, suppressions_from_candidates};
use stilyagi_ir::{IrError, IrNode, IrSuppression, is_directive_marker};
use tree_sitter::Node;

use super::helpers::{classify_doc_comment, node_flags, source_span, text_for_node};
use super::{RustIrBuilder, TREE_ID, root_node_id};

/// Collect Rust `// stilyagi:` directives and emit source-backed comment nodes.
pub(super) fn collect_comment_suppressions(
    builder: &mut RustIrBuilder<'_>,
    root: Node<'_>,
) -> (Vec<IrSuppression>, Vec<IrError>) {
    let mut comments = Vec::new();
    collect_comment_nodes(builder.source, root, &mut comments);
    comments.sort_by_key(|node| (node.start_byte(), node.end_byte()));

    let root_id = root_node_id();
    let mut candidates = Vec::new();
    for comment in comments {
        let Some(body) = comment_body(builder.source, comment) else {
            continue;
        };
        if !is_directive_marker(&body) {
            continue;
        }

        let span = source_span(comment);
        let node_id = builder.next_node_id();
        let node_id_string = node_id.to_string();
        builder.push_node(IrNode {
            id: node_id_string.clone(),
            tree: TREE_ID.to_owned(),
            kind: "comment".to_owned(),
            parent: Some(root_id.clone().into()),
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: BTreeMap::new(),
            span,
            flags: node_flags(comment),
        });
        builder.push_child(&root_id, &node_id);
        candidates.push(SuppressionCandidate {
            origin: node_id_string,
            span,
            body,
        });
    }

    suppressions_from_candidates(candidates)
}

fn collect_comment_nodes<'tree>(source: &str, node: Node<'tree>, comments: &mut Vec<Node<'tree>>) {
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        if current.kind() == "line_comment" && classify_doc_comment(source, current).is_none() {
            comments.push(current);
        }

        let mut cursor = current.walk();
        let mut children = current.named_children(&mut cursor).collect::<Vec<_>>();
        children.reverse();
        pending.extend(children);
    }
}

fn comment_body(source: &str, comment: Node<'_>) -> Option<String> {
    text_for_node(source, comment)?
        .strip_prefix("//")
        .map(ToOwned::to_owned)
}
