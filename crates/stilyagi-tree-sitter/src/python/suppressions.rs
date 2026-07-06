//! Comment-based suppression extraction for Python sources.

use std::collections::BTreeMap;
use stilyagi_ir::suppression::{SuppressionCandidate, suppressions_from_candidates};
use stilyagi_ir::{IrError, IrNode, IrSuppression, is_directive_marker};
use tree_sitter::Node;

use super::helpers::{collect_comment_nodes, comment_body, node_flags, source_span};
use super::{PythonIrBuilder, TREE_ID, root_node_id};

/// Collect Python `# stilyagi:` directives and emit source-backed comment nodes.
pub(super) fn collect_comment_suppressions(
    builder: &mut PythonIrBuilder<'_>,
    root: Node<'_>,
) -> (Vec<IrSuppression>, Vec<IrError>) {
    let mut comments = Vec::new();
    collect_comment_nodes(root, &mut comments);
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
            span: source_span(comment),
            flags: node_flags(comment),
        });
        builder.push_child(&root_id, &node_id);
        candidates.push(SuppressionCandidate {
            origin: node_id_string,
            span: source_span(comment),
            body,
        });
    }

    suppressions_from_candidates(candidates)
}
