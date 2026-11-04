//! Markdown AST node to lintable IR region emission.

mod node_attrs;

use std::collections::BTreeMap;

use markdown::mdast::Node;
use stilyagi_ir::{IrRegion, IrSegment, RegionKind, SegmentOrigin, SyntheticReason};

use self::node_attrs::{
    blockquote_attrs,
    blockquote_scope,
    image_attrs,
    link_attrs,
    list_item_attrs,
    list_item_scope,
    span_from_positioned_node,
};
use crate::{
    builder::{MarkdownIrBuilder, StructuralParent},
    flatten::{SourceNodeId, flatten_region},
};

/// Identity shared by the region constructors: the allocated region id, its
/// kind, and the originating AST node id.
struct RegionIdentity<'node> {
    /// Allocated region identifier, unique within the document.
    id: String,
    /// Region kind that determines the emitted `kind` and scope prefix.
    kind: RegionKind,
    /// Identifier of the AST node that produced the region.
    node_id: &'node str,
}

impl MarkdownIrBuilder<'_> {
    /// Emits the thin structural region for a list item or blockquote before
    /// its children are visited, returning the parent to track while they are.
    pub(super) fn push_preorder_region_for_node(
        &mut self,
        node: &Node,
        node_id: &str,
    ) -> Option<StructuralParent> {
        match node {
            Node::ListItem(list_item) => {
                let region_id = self.next_region_id();
                let kind = RegionKind::ListItem;
                self.regions.push(self.thin_region(
                    RegionIdentity {
                        id: region_id.clone(),
                        kind,
                        node_id,
                    },
                    list_item_scope(kind.as_str(), list_item, self.list_contexts.last()),
                    list_item_attrs(list_item, self.list_contexts.last()),
                ));
                Some(StructuralParent {
                    region_id,
                    scope_tag: "list_item",
                })
            }
            Node::Blockquote(_) => {
                self.blockquote_depth += 1;
                let region_id = self.next_region_id();
                let kind = RegionKind::Blockquote;
                self.regions.push(self.thin_region(
                    RegionIdentity {
                        id: region_id.clone(),
                        kind,
                        node_id,
                    },
                    blockquote_scope(kind.as_str(), self.blockquote_depth),
                    blockquote_attrs(self.blockquote_depth),
                ));
                Some(StructuralParent {
                    region_id,
                    scope_tag: "blockquote",
                })
            }
            _ => None,
        }
    }

    /// Emits the region for a node after its children, and unwinds the
    /// blockquote depth; list items are skipped as preorder-only.
    pub(super) fn push_postorder_region_for_node(&mut self, node: &Node, node_id: &str) {
        if matches!(node, Node::ListItem(_)) {
            return;
        }
        if matches!(node, Node::Blockquote(_)) {
            self.blockquote_depth = self.blockquote_depth.saturating_sub(1);
            return;
        }
        let region_kind = match node {
            Node::Heading(_) => Some(RegionKind::Heading),
            Node::Paragraph(_) => Some(RegionKind::Paragraph),
            Node::TableCell(_) => Some(RegionKind::TableCell),
            Node::Yaml(_) | Node::Toml(_) => Some(RegionKind::Frontmatter),
            Node::Image(image) if !image.alt.is_empty() => Some(RegionKind::ImageAlt),
            Node::Link(link) if link.title.as_deref().is_some_and(|title| !title.is_empty()) => {
                Some(RegionKind::LinkTitle)
            }
            _ => None,
        };
        if let Some(kind) = region_kind {
            let region_id = self.next_region_id();
            let identity = RegionIdentity {
                id: region_id,
                kind,
                node_id,
            };
            if let Some(emitted_region) = self.postorder_region(identity, node) {
                self.regions.push(emitted_region);
            }
        }
    }

    /// Dispatches to the constructor for the node's region kind, falling back
    /// to flattened inline emission.
    fn postorder_region(&self, identity: RegionIdentity<'_>, node: &Node) -> Option<IrRegion> {
        match node {
            Node::Yaml(_) => self.frontmatter_region(identity, "yaml", node),
            Node::Toml(_) => self.frontmatter_region(identity, "toml", node),
            Node::Image(image) => {
                Some(self.decoded_text_region(identity, &image.alt, image_attrs(image)))
            }
            Node::Link(link) => Some(self.decoded_text_region(
                identity,
                link.title.as_deref().unwrap_or_default(),
                link_attrs(link),
            )),
            _ => Some(self.flattened_region(identity, node)),
        }
    }

    /// Builds a region from the node's flattened inline text and segments,
    /// adding heading depth and table header attributes where relevant.
    fn flattened_region(&self, identity: RegionIdentity<'_>, node: &Node) -> IrRegion {
        let kind_name = identity.kind.as_str();
        let flattened = flatten_region(node, SourceNodeId::new(identity.node_id), self.source);
        let mut attrs = BTreeMap::new();
        if let Node::Heading(heading) = node {
            attrs.insert("depth".to_owned(), serde_json::json!(heading.depth));
        }
        if identity.kind == RegionKind::TableCell {
            let is_header = self
                .table_row_contexts
                .last()
                .is_some_and(|context| context.is_header);
            attrs.insert("header".to_owned(), serde_json::json!(is_header));
        }
        IrRegion {
            id: identity.id,
            kind: kind_name.to_owned(),
            scope: self.scope_for(kind_name, node),
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: flattened.text,
            segments: flattened.segments,
            origin_nodes: vec![identity.node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    /// Builds a structural region with no text or segments, used for list
    /// items and blockquotes whose content is emitted by descendant regions.
    fn thin_region(
        &self,
        identity: RegionIdentity<'_>,
        scope: Vec<String>,
        attrs: BTreeMap<String, serde_json::Value>,
    ) -> IrRegion {
        IrRegion {
            id: identity.id,
            kind: identity.kind.as_str().to_owned(),
            scope,
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: String::new(),
            segments: Vec::new(),
            origin_nodes: vec![identity.node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    /// Builds a source-backed region for YAML or TOML frontmatter.
    ///
    /// Returns `None` when the node has no position or its span falls outside
    /// the source.
    fn frontmatter_region(
        &self,
        identity: RegionIdentity<'_>,
        format: &str,
        node: &Node,
    ) -> Option<IrRegion> {
        let span = span_from_positioned_node(node)?;
        let text = self.source.get(span.byte_start..span.byte_end)?.to_owned();
        let segments = vec![IrSegment::new(
            0,
            text.clone(),
            SegmentOrigin::Source {
                span,
                node: identity.node_id.to_owned(),
            },
        )];
        let mut attrs = BTreeMap::new();
        attrs.insert("format".to_owned(), serde_json::json!(format));
        Some(IrRegion {
            id: identity.id,
            kind: RegionKind::Frontmatter.as_str().to_owned(),
            scope: vec![
                "markdown".to_owned(),
                RegionKind::Frontmatter.as_str().to_owned(),
                format.to_owned(),
            ],
            syntax: "markdown".to_owned(),
            natural_language: None,
            text,
            segments,
            origin_nodes: vec![identity.node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        })
    }

    /// Builds a region for decoded text (alt text, link titles); empty yields none.
    fn decoded_text_region(
        &self,
        identity: RegionIdentity<'_>,
        text: &str,
        attrs: BTreeMap<String, serde_json::Value>,
    ) -> IrRegion {
        let segments = if text.is_empty() {
            Vec::new()
        } else {
            vec![IrSegment::new(
                0,
                text.to_owned(),
                SegmentOrigin::Synthetic {
                    reason: SyntheticReason::DecodedText,
                },
            )]
        };
        IrRegion {
            id: identity.id,
            kind: identity.kind.as_str().to_owned(),
            scope: self.decoded_text_scope(identity.kind.as_str()),
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: text.to_owned(),
            segments,
            origin_nodes: vec![identity.node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    /// Builds the scope for decoded text: the Markdown root, the region kind,
    /// `decoded`, then the enclosing structural scope tags.
    fn decoded_text_scope(&self, kind: &str) -> Vec<String> {
        let mut scope = vec!["markdown".to_owned(), kind.to_owned(), "decoded".to_owned()];
        for parent in &self.parent_regions {
            scope.push(parent.scope_tag.to_owned());
        }
        scope
    }

    /// Builds the scope for a flattened region, adding heading depth or table
    /// header/body position and the enclosing structural scope tags.
    fn scope_for(&self, kind: &str, node: &Node) -> Vec<String> {
        let mut scope = vec!["markdown".to_owned(), kind.to_owned()];
        if let Node::Heading(heading) = node {
            scope.push(format!("h{}", heading.depth));
        }
        if kind == RegionKind::TableCell.as_str() {
            let table_scope = if self
                .table_row_contexts
                .last()
                .is_some_and(|context| context.is_header)
            {
                "header"
            } else {
                "body"
            };
            scope.push(table_scope.to_owned());
        }
        for parent in &self.parent_regions {
            scope.push(parent.scope_tag.to_owned());
        }
        scope
    }

    /// Returns the id of the innermost structural parent region, if any.
    fn current_parent_region_id(&self) -> Option<String> {
        self.parent_regions
            .last()
            .map(|parent| parent.region_id.clone())
    }
}

#[cfg(test)]
mod tests {
    //! Regression tests for Markdown region emission edge cases.

    use markdown::mdast::{Node, Yaml};
    use rstest::rstest;

    use crate::builder::MarkdownIrBuilder;

    #[rstest]
    fn frontmatter_without_position_does_not_emit_empty_region() {
        let mut builder = MarkdownIrBuilder::new("---\ntitle: Example\n---");
        let node = Node::Yaml(Yaml {
            value: "title: Example".to_owned(),
            position: None,
        });

        builder.push_postorder_region_for_node(&node, "n0");

        assert_eq!(builder.regions, []);
    }
}
