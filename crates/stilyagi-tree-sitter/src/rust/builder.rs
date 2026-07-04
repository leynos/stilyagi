//! Internal builder for Rust documentation-comment extraction.

use std::collections::{BTreeMap, HashMap};

use stilyagi_ir::{IrError, IrNode, IrRegion, NodeFlags};
use tree_sitter::Node;

use super::builder_state::{
    DocCommentEntry, DocCommentGroup, DocCommentRegionParts, NonDocCommentState, push_group,
};
use super::helpers::{
    classify_doc_comment, collect_recovery_nodes, current_owner_node_id, doc_comment_content_span,
    is_recovery_node, item_body, line_comment_content_end, node_flags, owner_frame_for_item,
    source_span, text_for_field,
};
use super::owner::{OwnerFrame, owner_for};
use super::types::{NodeId, NodeKind};

const TREE_ID: &str = "t0";

/// Stateful builder for owner-aware Rust doc-comment IR.
pub(super) struct RustIrBuilder<'source> {
    source: &'source str,
    next_node: usize,
    next_region: usize,
    nodes: Vec<IrNode>,
    node_positions: HashMap<String, usize>,
    regions: Vec<IrRegion>,
    errors: Vec<IrError>,
}

impl<'source> RustIrBuilder<'source> {
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

    pub(super) fn into_ir(self) -> (Vec<IrNode>, Vec<IrRegion>, Vec<IrError>) {
        (self.nodes, self.regions, self.errors)
    }

    pub(super) fn push_module_root(&mut self, root: Node<'_>) {
        let node_id = self.next_node_id();
        debug_assert_eq!(node_id.as_str(), super::root_node_id().as_str());
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

    pub(super) fn push_recovery_errors(&mut self, root: Node<'_>) {
        let mut nodes = Vec::new();
        collect_recovery_nodes(root, &mut nodes);
        nodes.sort_by_key(|node| (node.start_byte(), node.end_byte()));
        for node in nodes {
            let span = source_span(node);
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

            let Some(flavor) = classify_doc_comment(self.source, child) else {
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

            let Some(content_span) = doc_comment_content_span(self.source, child, flavor) else {
                self.record_doc_comment_span_error(child);
                continue;
            };
            let entry = DocCommentEntry {
                node: child,
                flavor,
                content: self.doc_comment_content(child, flavor),
                content_span,
            };
            if flavor.is_inner() {
                push_group(self.source, &mut pending_inner, entry);
            } else {
                push_group(self.source, &mut pending_outer, entry);
            }
        }

        self.flush_pending_groups(stack, &mut pending_inner, None);
    }

    fn visit_owner_item(
        &mut self,
        child: Node<'source>,
        frame: OwnerFrame,
        state: &mut NonDocCommentState<'_, 'source>,
    ) {
        state.stack.push(frame);
        let owner_node_id = self.push_owner_node(child, state.stack);
        self.flush_pending_groups(
            state.stack,
            state.pending_outer,
            Some(owner_node_id.clone()),
        );
        self.visit_item_body(child, state.stack, state.depth + 1);
        let _ = state.stack.pop();
    }

    fn handle_non_doc_child(
        &mut self,
        child: Node<'source>,
        state: &mut NonDocCommentState<'_, 'source>,
    ) {
        let Some(frame) = owner_frame_for_item(self.source, child) else {
            state.pending_outer.clear();
            state.pending_inner.clear();
            return;
        };

        self.visit_owner_item(child, frame, state);
    }

    fn visit_item_body(&mut self, node: Node<'source>, stack: &mut Vec<OwnerFrame>, depth: usize) {
        if let Some(body) = item_body(node) {
            self.visit_container(body, stack, depth);
        }
    }

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

    fn push_doc_comment_group(
        &mut self,
        group: &DocCommentGroup<'source>,
        owner_node_id: &NodeId,
        owner: stilyagi_ir::IrOwner,
    ) {
        let mut text = String::new();
        let mut segments = Vec::new();
        let mut origin_nodes = Vec::new();
        let mut region = DocCommentRegionParts {
            text: &mut text,
            segments: &mut segments,
        };

        for (index, entry) in group.entries.iter().enumerate() {
            let entry_node_id = self.next_node_id();
            let entry_node_id_string = entry_node_id.to_string();
            self.push_node(IrNode {
                id: entry_node_id_string.clone(),
                tree: TREE_ID.to_owned(),
                kind: entry.node.kind().to_owned(),
                parent: Some(owner_node_id.clone().into()),
                children: Vec::new(),
                fields: BTreeMap::new(),
                props: BTreeMap::new(),
                span: source_span(entry.node),
                flags: node_flags(entry.node),
            });
            self.push_child(owner_node_id, &entry_node_id);
            origin_nodes.push(entry_node_id_string);

            if index > 0 {
                region.push_synthetic_segment(" ");
            }
            region.push_source_segment(&entry.content, entry.content_span, entry_node_id);
        }

        let region_id = self.next_region_id();
        self.regions.push(IrRegion {
            id: region_id,
            kind: "rust_doc_comment".to_owned(),
            scope: vec![
                "rust".to_owned(),
                "doc_comment".to_owned(),
                owner.kind.clone(),
            ],
            syntax: "rust".to_owned(),
            natural_language: None,
            text,
            segments,
            origin_nodes,
            owner: Some(owner),
            attrs: BTreeMap::new(),
            parent_region: None,
        });
    }

    fn push_owner_node(&mut self, node: Node<'source>, stack: &mut [OwnerFrame]) -> NodeId {
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
        if matches!(node.kind(), "impl_item") {
            if let Some(self_type) = text_for_field(self.source, node, "type")
                .or_else(|| text_for_field(self.source, node, "self_type"))
            {
                fields.insert("type".to_owned(), self_type);
            }
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

    fn doc_comment_content(
        &self,
        node: Node<'source>,
        flavor: super::helpers::DocCommentFlavor,
    ) -> String {
        let start = node.start_byte();
        match flavor {
            super::helpers::DocCommentFlavor::OuterLine
            | super::helpers::DocCommentFlavor::InnerLine => {
                let end = line_comment_content_end(self.source, node);
                self.source
                    .get(start + 3..end)
                    .unwrap_or_default()
                    .to_owned()
            }
            super::helpers::DocCommentFlavor::OuterBlock
            | super::helpers::DocCommentFlavor::InnerBlock => {
                let end = node.end_byte();
                self.source
                    .get(start + 3..end.saturating_sub(2))
                    .unwrap_or_default()
                    .to_owned()
            }
        }
    }

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
                "stopped Rust doc-comment traversal at the maximum depth of \
                 {} at bytes {}..{}",
                super::MAX_TRAVERSAL_DEPTH,
                span.byte_start,
                span.byte_end
            ),
            span: Some(span),
        });
    }

    fn record_doc_comment_span_error(&mut self, node: Node<'source>) {
        let span = source_span(node);
        self.errors.push(IrError {
            code: "rust-doc-comment-span".to_owned(),
            message: "failed to derive Rust doc-comment content span".to_owned(),
            span: Some(span),
        });
    }

    fn push_node(&mut self, node: IrNode) {
        let index = self.nodes.len();
        self.node_positions.insert(node.id.clone(), index);
        self.nodes.push(node);
    }

    fn push_child(&mut self, parent_id: &NodeId, child_id: &NodeId) {
        if let Some(parent) = self
            .node_positions
            .get(parent_id.as_str())
            .and_then(|index| self.nodes.get_mut(*index))
        {
            parent.children.push(child_id.clone().into());
        }
    }

    fn next_node_id(&mut self) -> NodeId {
        let id = NodeId(format!("n{}", self.next_node));
        self.next_node += 1;
        id
    }

    fn next_region_id(&mut self) -> String {
        let id = format!("r{}", self.next_region);
        self.next_region += 1;
        id
    }
}
