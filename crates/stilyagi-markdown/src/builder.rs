//! Markdown AST traversal and IR node assembly.

use std::collections::BTreeMap;

use markdown::{mdast::Node, message::Message};
use stilyagi_ir::{IrNode, IrRegion, NodeFlags};

use crate::{MarkdownDiagnosticContext, node_kind::node_kind, source_span};

pub(super) struct MarkdownIrBuilder<'source> {
    pub(super) source: &'source str,
    pub(super) next_node: usize,
    pub(super) next_region: usize,
    pub(super) nodes: Vec<IrNode>,
    pub(super) regions: Vec<IrRegion>,
    pub(super) parent_regions: Vec<StructuralParent>,
    pub(super) list_contexts: Vec<ListContext>,
    pub(super) table_row_contexts: Vec<TableRowContext>,
    pub(super) blockquote_depth: usize,
}

#[derive(Debug, Clone)]
pub(super) struct StructuralParent {
    pub(super) region_id: String,
    pub(super) scope_tag: &'static str,
}

#[derive(Debug, Clone, Copy)]
pub(super) struct ListContext {
    pub(super) ordered: bool,
    pub(super) start: Option<u32>,
}

#[derive(Debug, Clone, Copy)]
pub(super) struct TableRowContext {
    pub(super) is_header: bool,
}

impl<'source> MarkdownIrBuilder<'source> {
    pub(super) const fn new(source: &'source str) -> Self {
        Self {
            source,
            next_node: 0,
            next_region: 0,
            nodes: Vec::new(),
            regions: Vec::new(),
            parent_regions: Vec::new(),
            list_contexts: Vec::new(),
            table_row_contexts: Vec::new(),
            blockquote_depth: 0,
        }
    }

    pub(super) fn push_node(
        &mut self,
        node: &Node,
        parent: Option<&str>,
        context: &MarkdownDiagnosticContext<'_>,
    ) -> Result<String, Message> {
        let node_id = self.next_node_id();
        let node_index = self.nodes.len();
        self.nodes.push(IrNode {
            id: node_id.clone(),
            tree: "t0".to_owned(),
            kind: node_kind(node).to_owned(),
            parent: parent.map(str::to_owned),
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: node_props(node),
            span: source_span(node, context)?,
            flags: NodeFlags::named_source(),
        });

        let structural_parent = self.push_preorder_region_for_node(node, &node_id);
        if let Some(structural_region) = structural_parent.clone() {
            self.parent_regions.push(structural_region);
        }
        let mut child_ids = Vec::new();
        self.push_child_nodes(node, &node_id, context, &mut child_ids)?;
        if structural_parent.is_some() {
            self.parent_regions.pop();
        }

        if let Some(stored_node) = self.nodes.get_mut(node_index) {
            stored_node.children = child_ids;
        }
        self.push_postorder_region_for_node(node, &node_id);
        Ok(node_id)
    }

    fn push_child_nodes(
        &mut self,
        node: &Node,
        node_id: &str,
        context: &MarkdownDiagnosticContext<'_>,
        child_ids: &mut Vec<String>,
    ) -> Result<(), Message> {
        match node {
            Node::List(list) => {
                self.list_contexts.push(ListContext {
                    ordered: list.ordered,
                    start: list.start,
                });
                for child in &list.children {
                    child_ids.push(self.push_node(child, Some(node_id), context)?);
                }
                self.list_contexts.pop();
            }
            Node::Table(table) => {
                for (row_index, child) in table.children.iter().enumerate() {
                    self.table_row_contexts.push(TableRowContext {
                        is_header: row_index == 0,
                    });
                    child_ids.push(self.push_node(child, Some(node_id), context)?);
                    self.table_row_contexts.pop();
                }
            }
            _ => {
                if let Some(children) = node.children() {
                    for child in children {
                        child_ids.push(self.push_node(child, Some(node_id), context)?);
                    }
                }
            }
        }
        Ok(())
    }

    pub(super) fn next_region_id(&mut self) -> String {
        let id = format!("r{}", self.next_region);
        self.next_region += 1;
        id
    }

    fn next_node_id(&mut self) -> String {
        let id = format!("n{}", self.next_node);
        self.next_node += 1;
        id
    }
}

fn node_props(node: &Node) -> BTreeMap<String, serde_json::Value> {
    let mut props = BTreeMap::new();
    if let Node::Heading(heading) = node {
        props.insert("depth".to_owned(), serde_json::json!(heading.depth));
    }
    props
}
