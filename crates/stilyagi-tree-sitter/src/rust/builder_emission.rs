//! Emit grouped Rust documentation comments into the builder's IR storage.
//!
//! This child shares the parent builder's private state without exposing its
//! fields or introducing a reusable extraction interface.

use std::collections::BTreeMap;

use stilyagi_ir::{IrNode, IrRegion, RegionKind};

use super::super::builder_state::{DocCommentGroup, DocCommentRegionParts};
use super::super::helpers::{node_flags, source_span};
use super::super::types::NodeId;
use super::{RustIrBuilder, TREE_ID};

impl<'source> RustIrBuilder<'source> {
    pub(super) fn push_doc_comment_group(
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
            kind: RegionKind::RustDocComment.as_str().to_owned(),
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

    fn next_region_id(&mut self) -> String {
        let id = format!("r{}", self.next_region);
        self.next_region += 1;
        id
    }
}
