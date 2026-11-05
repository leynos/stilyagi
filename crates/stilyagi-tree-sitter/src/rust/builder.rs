//! Internal builder for Rust documentation-comment extraction.

#[path = "builder_emission.rs"]
mod emission;

use std::collections::{BTreeMap, HashMap};

use stilyagi_ir::{IrError, IrNode, IrRegion, NodeFlags};
use tree_sitter::Node;

use super::{
    builder_state::{DocCommentEntry, DocCommentGroup, NonDocCommentState, push_group},
    helpers::{
        classify_doc_comment,
        collect_recovery_nodes,
        current_owner_node_id,
        doc_comment_content,
        doc_comment_content_span,
        is_recovery_node,
        item_body,
        module_body_has_leading_inner_docs,
        node_flags,
        owner_frame_for_item,
        recovery_doc_comment_count,
        source_span,
        text_for_field,
    },
    owner::{OwnerFrame, owner_for},
    types::{NodeId, NodeKind},
};

/// Identifier of the single IR tree emitted for a Rust source file.
const TREE_ID: &str = "t0";

/// Stateful builder for owner-aware Rust doc-comment IR.
pub(super) struct RustIrBuilder<'source> {
    /// Source text the builder indexes spans and comments against.
    pub(super) source: &'source str,
    /// Next numeric suffix to allocate for a node identifier.
    next_node: usize,
    /// Next numeric suffix to allocate for a region identifier.
    next_region: usize,
    /// Emitted IR nodes in insertion order.
    nodes: Vec<IrNode>,
    /// Maps each emitted node id to its index in `nodes`.
    node_positions: HashMap<String, usize>,
    /// Emitted doc-comment regions in insertion order.
    regions: Vec<IrRegion>,
    /// Recoverable extraction errors accumulated during traversal.
    errors: Vec<IrError>,
}

impl<'source> RustIrBuilder<'source> {
    /// Create an empty builder over `source`.
    pub(super) fn new(source: &'source str) -> Self {
        Self {
            source,
            next_node: 0,
            next_region: 0,
            nodes: Vec::new(),
            node_positions: HashMap::new(),
            regions: Vec::new(),
            errors: Vec::new(),
        }
    }

    /// Consume the builder, returning its nodes, regions, and errors.
    pub(super) fn into_ir(self) -> (Vec<IrNode>, Vec<IrRegion>, Vec<IrError>) {
        (self.nodes, self.regions, self.errors)
    }

    /// Emit the module root node, which must receive the first node id.
    pub(super) fn push_module_root(&mut self, root: Node<'_>) {
        let node_id = self.next_node_id();
        debug_assert_eq!(
            node_id.as_str(),
            super::root_node_id().as_str(),
            "module root must receive the first node id"
        );
        self.push_node(IrNode {
            id: node_id.into(),
            tree: TREE_ID.to_owned(),
            kind: NodeKind("module").as_str().to_owned(),
            parent: None,
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: BTreeMap::new(),
            span: source_span(root),
            flags: NodeFlags::named_source(),
        });
    }

    /// Record a parse-recovery error for each recovered node in source order,
    /// including any doc comments absorbed into the broken subtree.
    pub(super) fn push_recovery_errors(&mut self, root: Node<'_>) {
        let mut nodes = Vec::new();
        collect_recovery_nodes(root, &mut nodes);
        nodes.sort_by_key(|node| (node.start_byte(), node.end_byte()));
        for node in nodes {
            let span = source_span(node);
            self.record_recovery_doc_comment_drop(
                node,
                recovery_doc_comment_count(self.source, node),
            );
            self.errors.push(IrError {
                code: "rust-parse-recovery".to_owned(),
                message: format!(
                    "recovered {} node at bytes {}..{}",
                    node.kind(),
                    span.byte_start,
                    span.byte_end
                ),
                span: Some(span),
            });
        }
    }

    /// Walk a container's named children, grouping doc comments and
    /// descending into owner items until the traversal depth limit is reached.
    pub(super) fn visit_container(
        &mut self,
        node: Node<'source>,
        stack: &mut Vec<OwnerFrame>,
        depth: usize,
    ) {
        if depth >= super::MAX_TRAVERSAL_DEPTH {
            self.record_depth_limit(node);
            return;
        }

        let mut pending_outer = Vec::new();
        let mut pending_inner = Vec::new();
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            if is_recovery_node(child) {
                pending_outer.clear();
                pending_inner.clear();
                continue;
            }

            let Some(flavour) = classify_doc_comment(self.source, child) else {
                self.flush_pending_groups(stack, &mut pending_inner, None);
                let mut state = NonDocCommentState {
                    stack,
                    pending_outer: &mut pending_outer,
                    pending_inner: &mut pending_inner,
                    depth,
                };
                self.handle_non_doc_child(child, &mut state);
                continue;
            };

            let Some(content_span) = doc_comment_content_span(self.source, child, flavour) else {
                self.record_doc_comment_span_error(child);
                continue;
            };
            let entry = DocCommentEntry {
                node: child,
                flavour,
                content: doc_comment_content(self.source, child, flavour),
                content_span,
            };
            if flavour.is_inner() {
                push_group(self.source, &mut pending_inner, entry);
            } else {
                push_group(self.source, &mut pending_outer, entry);
            }
        }

        self.flush_pending_groups(stack, &mut pending_inner, None);
    }

    /// Push an owner frame, emit its node when it owns docs, and visit its
    /// body.
    fn visit_owner_item(
        &mut self,
        child: Node<'source>,
        frame: OwnerFrame,
        state: &mut NonDocCommentState<'_, 'source>,
    ) {
        let should_emit_owner = !state.pending_outer.is_empty()
            || module_body_has_leading_inner_docs(self.source, child);
        state.stack.push(frame);
        if should_emit_owner {
            let owner_node_id = self.push_owner_node(child, state.stack);
            self.flush_pending_groups(
                state.stack,
                state.pending_outer,
                Some(owner_node_id.clone()),
            );
        }
        self.visit_item_body(child, state.stack, state.depth + 1);
        let _ = state.stack.pop();
    }

    /// Skip attributes and comments, or visit the child as an owner item.
    fn handle_non_doc_child(
        &mut self,
        child: Node<'source>,
        state: &mut NonDocCommentState<'_, 'source>,
    ) {
        if matches!(
            child.kind(),
            "attribute_item" | "inner_attribute_item" | "line_comment" | "block_comment"
        ) {
            return;
        }

        let Some(frame) = owner_frame_for_item(self.source, child) else {
            state.pending_outer.clear();
            state.pending_inner.clear();
            return;
        };

        self.visit_owner_item(child, frame, state);
    }

    /// Visit the body of an item when it has one.
    fn visit_item_body(&mut self, node: Node<'source>, stack: &mut Vec<OwnerFrame>, depth: usize) {
        if let Some(body) = item_body(node) {
            self.visit_container(body, stack, depth);
        }
    }

    /// Emit queued doc-comment groups against the given or current owner.
    fn flush_pending_groups(
        &mut self,
        stack: &[OwnerFrame],
        groups: &mut Vec<DocCommentGroup<'source>>,
        owner_node_id: Option<NodeId>,
    ) {
        if groups.is_empty() {
            return;
        }

        let resolved_owner_node_id = owner_node_id.unwrap_or_else(|| current_owner_node_id(stack));
        let owner = owner_for(stack);
        for group in groups.drain(..) {
            self.push_doc_comment_group(&group, &resolved_owner_node_id, owner.clone());
        }
    }

    /// Emit or reuse the IR node for the current owner frame and return its
    /// id.
    pub(super) fn push_owner_node(
        &mut self,
        node: Node<'source>,
        stack: &mut [OwnerFrame],
    ) -> NodeId {
        let current_index = stack.len().saturating_sub(1);
        if let Some(node_id) = stack
            .get(current_index)
            .and_then(|owner| owner.emitted_node_id.clone())
        {
            return node_id;
        }

        let parent = current_owner_node_id(stack);
        let node_id = self.next_node_id();
        let mut fields = BTreeMap::new();
        if let Some(name) = text_for_field(self.source, node, "name") {
            fields.insert("name".to_owned(), name);
        }
        if matches!(node.kind(), "impl_item")
            && let Some(self_type) = text_for_field(self.source, node, "type")
                .or_else(|| text_for_field(self.source, node, "self_type"))
        {
            fields.insert("type".to_owned(), self_type);
        }
        self.push_node(IrNode {
            id: node_id.clone().into(),
            tree: TREE_ID.to_owned(),
            kind: node.kind().to_owned(),
            parent: Some(parent.clone().into()),
            children: Vec::new(),
            fields,
            props: BTreeMap::new(),
            span: source_span(node),
            flags: node_flags(node),
        });
        self.push_child(&parent, &node_id);
        if let Some(owner) = stack.get_mut(current_index) {
            owner.emitted_node_id = Some(node_id.clone());
        }
        node_id
    }

    /// Record a traversal-depth-limit error and warn about the truncated
    /// subtree.
    fn record_depth_limit(&mut self, node: Node<'source>) {
        let span = source_span(node);
        tracing::warn!(
            byte_start = span.byte_start,
            byte_end = span.byte_end,
            max_depth = super::MAX_TRAVERSAL_DEPTH,
            "rust doc-comment traversal stopped at the maximum tree depth"
        );
        self.errors.push(IrError {
            code: "rust-traversal-depth-limit".to_owned(),
            message: format!(
                "stopped Rust doc-comment traversal at the maximum depth of {} at bytes {}..{}",
                super::MAX_TRAVERSAL_DEPTH,
                span.byte_start,
                span.byte_end
            ),
            span: Some(span),
        });
    }

    /// Record an error for a doc comment whose content span could not be
    /// derived.
    fn record_doc_comment_span_error(&mut self, node: Node<'source>) {
        let span = source_span(node);
        self.errors.push(IrError {
            code: "rust-doc-comment-span".to_owned(),
            message: "failed to derive Rust doc-comment content span".to_owned(),
            span: Some(span),
        });
    }

    /// Record an error when a recovered subtree absorbed one or more doc
    /// comments.
    fn record_recovery_doc_comment_drop(&mut self, node: Node<'_>, count: usize) {
        if count == 0 {
            return;
        }
        let span = source_span(node);
        self.errors.push(IrError {
            code: "rust-doc-comment-error-subtree".to_owned(),
            message: "dropped Rust doc comment(s) absorbed into a tree-sitter ERROR subtree"
                .to_owned(),
            span: Some(span),
        });
    }

    /// Append a node and index its id for later child attachment.
    pub(super) fn push_node(&mut self, node: IrNode) {
        let index = self.nodes.len();
        self.node_positions.insert(node.id.clone(), index);
        self.nodes.push(node);
    }

    /// Attach `child_id` to `parent_id` when the parent has been emitted.
    pub(super) fn push_child(&mut self, parent_id: &NodeId, child_id: &NodeId) {
        if let Some(parent) = self
            .node_positions
            .get(parent_id.as_str())
            .and_then(|index| self.nodes.get_mut(*index))
        {
            parent.children.push(child_id.clone().into());
        }
    }

    /// Allocate the next node identifier, formatted as `n{n}`.
    pub(super) fn next_node_id(&mut self) -> NodeId {
        let id = NodeId(format!("n{}", self.next_node));
        self.next_node += 1;
        id
    }
}
