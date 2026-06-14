//! Markdown AST node to lintable IR region emission.

use std::collections::BTreeMap;

use markdown::mdast::Node;
use stilyagi_ir::{IrRegion, IrSegment, RegionKind, SegmentOrigin, SourceSpan, SyntheticReason};

use crate::builder::{ListContext, MarkdownIrBuilder, StructuralParent};
use crate::flatten::{SourceNodeId, flatten_region};

impl MarkdownIrBuilder<'_> {
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
                    region_id.clone(),
                    kind,
                    list_item_scope(kind.as_str(), list_item, self.list_contexts.last()),
                    list_item_attrs(list_item, self.list_contexts.last()),
                    node_id,
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
                    region_id.clone(),
                    kind,
                    blockquote_scope(kind.as_str(), self.blockquote_depth),
                    blockquote_attrs(self.blockquote_depth),
                    node_id,
                ));
                Some(StructuralParent {
                    region_id,
                    scope_tag: "blockquote",
                })
            }
            _ => None,
        }
    }

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
            Node::Link(link) if link.title.is_some() => Some(RegionKind::LinkTitle),
            _ => None,
        };
        if let Some(kind) = region_kind {
            let kind_name = kind.as_str();
            let region_id = self.next_region_id();
            let region = match node {
                Node::Yaml(_) => self.frontmatter_region(region_id, "yaml", node, node_id),
                Node::Toml(_) => self.frontmatter_region(region_id, "toml", node, node_id),
                Node::Image(image) => self.decoded_text_region(
                    region_id,
                    kind,
                    &image.alt,
                    image_attrs(image),
                    node_id,
                ),
                Node::Link(link) => self.decoded_text_region(
                    region_id,
                    kind,
                    link.title.as_deref().unwrap_or_default(),
                    link_attrs(link),
                    node_id,
                ),
                _ => self.flattened_region(region_id, kind, kind_name, node, node_id),
            };
            self.regions.push(region);
        }
    }

    fn flattened_region(
        &self,
        region_id: String,
        kind: RegionKind,
        kind_name: &str,
        node: &Node,
        node_id: &str,
    ) -> IrRegion {
        let flattened = flatten_region(node, SourceNodeId::new(node_id), self.source);
        let mut attrs = BTreeMap::new();
        if let Node::Heading(heading) = node {
            attrs.insert("depth".to_owned(), serde_json::json!(heading.depth));
        }
        if kind == RegionKind::TableCell {
            let is_header = self
                .table_row_contexts
                .last()
                .is_some_and(|context| context.is_header);
            attrs.insert("header".to_owned(), serde_json::json!(is_header));
        }
        IrRegion {
            id: region_id,
            kind: kind_name.to_owned(),
            scope: self.scope_for(kind_name, node),
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: flattened.text,
            segments: flattened.segments,
            origin_nodes: vec![node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    fn thin_region(
        &self,
        region_id: String,
        kind: RegionKind,
        scope: Vec<String>,
        attrs: BTreeMap<String, serde_json::Value>,
        node_id: &str,
    ) -> IrRegion {
        IrRegion {
            id: region_id,
            kind: kind.as_str().to_owned(),
            scope,
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: String::new(),
            segments: Vec::new(),
            origin_nodes: vec![node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    fn frontmatter_region(
        &self,
        region_id: String,
        format: &str,
        node: &Node,
        node_id: &str,
    ) -> IrRegion {
        let span = span_from_positioned_node(node);
        let text = span
            .and_then(|source_span| {
                self.source
                    .get(source_span.byte_start..source_span.byte_end)
            })
            .unwrap_or_default()
            .to_owned();
        let segments = span
            .map(|source_span| {
                vec![IrSegment::new(
                    0,
                    text.clone(),
                    SegmentOrigin::Source {
                        span: source_span,
                        node: node_id.to_owned(),
                    },
                )]
            })
            .unwrap_or_default();
        let mut attrs = BTreeMap::new();
        attrs.insert("format".to_owned(), serde_json::json!(format));
        IrRegion {
            id: region_id,
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
            origin_nodes: vec![node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    fn decoded_text_region(
        &self,
        region_id: String,
        kind: RegionKind,
        text: &str,
        attrs: BTreeMap<String, serde_json::Value>,
        node_id: &str,
    ) -> IrRegion {
        let segments = if text.is_empty() {
            Vec::new()
        } else {
            vec![IrSegment::new(
                0,
                text.to_owned(),
                SegmentOrigin::Synthetic {
                    reason: SyntheticReason::DecodedText.as_str().to_owned(),
                },
            )]
        };
        IrRegion {
            id: region_id,
            kind: kind.as_str().to_owned(),
            scope: self.decoded_text_scope(kind.as_str()),
            syntax: "markdown".to_owned(),
            natural_language: None,
            text: text.to_owned(),
            segments,
            origin_nodes: vec![node_id.to_owned()],
            owner: None,
            attrs,
            parent_region: self.current_parent_region_id(),
        }
    }

    fn decoded_text_scope(&self, kind: &str) -> Vec<String> {
        let mut scope = vec!["markdown".to_owned(), kind.to_owned(), "decoded".to_owned()];
        for parent in &self.parent_regions {
            scope.push(parent.scope_tag.to_owned());
        }
        scope
    }

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

    fn current_parent_region_id(&self) -> Option<String> {
        self.parent_regions
            .last()
            .map(|parent| parent.region_id.clone())
    }
}

fn list_item_scope(
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

fn list_item_attrs(
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

fn blockquote_scope(kind: &str, depth: usize) -> Vec<String> {
    vec![
        "markdown".to_owned(),
        kind.to_owned(),
        format!("depth{depth}"),
    ]
}

fn blockquote_attrs(depth: usize) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("depth".to_owned(), serde_json::json!(depth));
    attrs
}

fn image_attrs(image: &markdown::mdast::Image) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("url".to_owned(), serde_json::json!(image.url));
    attrs.insert("source_backed".to_owned(), serde_json::json!(false));
    if let Some(title) = image.title.as_ref() {
        attrs.insert("title".to_owned(), serde_json::json!(title));
    }
    attrs
}

fn link_attrs(link: &markdown::mdast::Link) -> BTreeMap<String, serde_json::Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("url".to_owned(), serde_json::json!(link.url));
    attrs.insert("source_backed".to_owned(), serde_json::json!(false));
    if let Some(title) = link.title.as_ref() {
        attrs.insert("title".to_owned(), serde_json::json!(title));
    }
    attrs
}

fn span_from_positioned_node(node: &Node) -> Option<SourceSpan> {
    let position = node.position()?;
    SourceSpan::new(position.start.offset, position.end.offset)
}
