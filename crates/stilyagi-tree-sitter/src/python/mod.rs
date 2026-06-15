//! Python docstring extraction backed by `tree-sitter-python`.

mod helpers;
mod owner;
mod support;

use std::collections::BTreeMap;

use stilyagi_ir::{
    DocumentMetadata, IrDocument, IrError, IrNode, IrRegion, IrSegment, IrTree, NodeFlags,
    SegmentOrigin, SourceIdentity,
};
use tree_sitter::Node;

use helpers::{
    collect_error_nodes, definition_docstring, docstring_content, module_docstring,
    nearest_emitted_owner, node_flags, owner_frame_for_definition, source_span,
};
use owner::{OwnerFrame, owner_for};
use support::{parse_python, python_producer, validate_ir_consistency};

const TREE_ID: &str = "t0";

/// Fatal failure while building Python docstring IR.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PythonExtractError {
    /// The Python grammar failed to load into the parser.
    GrammarLoad,
    /// tree-sitter returned no parse tree for the source.
    NoParseTree,
}

impl std::fmt::Display for PythonExtractError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::GrammarLoad => formatter.write_str("failed to load tree-sitter-python grammar"),
            Self::NoParseTree => formatter.write_str("tree-sitter returned no Python parse tree"),
        }
    }
}

impl std::error::Error for PythonExtractError {}

/// Build an owner-aware Python docstring IR document.
///
/// # Errors
///
/// Returns a fatal extraction error only when the grammar cannot be loaded or
/// no parse tree can be produced. Recoverable parse anomalies belong in the IR
/// document `errors` list.
pub fn python_docstring_ir_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<IrDocument, PythonExtractError> {
    let tree = parse_python(source)?;
    let root = tree.root_node();
    let mut document = IrDocument::empty(
        DocumentMetadata::new("python", identity.path, identity.uri, source),
        vec![python_producer()],
        source,
    );
    document.trees.push(IrTree {
        id: TREE_ID.to_owned(),
        family: "tree-sitter".to_owned(),
        syntax: "python".to_owned(),
        root: "n0".to_owned(),
    });

    let mut builder = PythonIrBuilder::new(source);
    builder.push_module_root(root);
    builder.push_recovery_errors(root);
    builder.visit_module(root);

    document.nodes = builder.nodes;
    document.regions = builder.regions;
    document.errors = builder.errors;
    validate_ir_consistency(&document, source);
    Ok(document)
}

struct PythonIrBuilder<'source> {
    source: &'source str,
    next_node: usize,
    next_region: usize,
    nodes: Vec<IrNode>,
    regions: Vec<IrRegion>,
    errors: Vec<IrError>,
}

impl<'source> PythonIrBuilder<'source> {
    const fn new(source: &'source str) -> Self {
        Self {
            source,
            next_node: 0,
            next_region: 0,
            nodes: Vec::new(),
            regions: Vec::new(),
            errors: Vec::new(),
        }
    }

    fn push_module_root(&mut self, root: Node<'_>) {
        let node_id = self.next_node_id();
        debug_assert_eq!(node_id, "n0");
        self.nodes.push(IrNode {
            id: node_id,
            tree: TREE_ID.to_owned(),
            kind: "module".to_owned(),
            parent: None,
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: BTreeMap::new(),
            span: source_span(root),
            flags: NodeFlags::named_source(),
        });
    }

    fn push_recovery_errors(&mut self, root: Node<'_>) {
        let mut errors = Vec::new();
        collect_error_nodes(root, &mut errors);
        errors.sort_by_key(|node| (node.start_byte(), node.end_byte()));
        for node in errors {
            let span = source_span(node);
            self.errors.push(IrError {
                code: "python-parse-recovery".to_owned(),
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

    fn visit_module(&mut self, root: Node<'_>) {
        let mut stack = Vec::new();
        if let Some(docstring) = module_docstring(self.source, root) {
            self.push_docstring_region(docstring, &stack, "n0");
        }
        self.visit_children(root, &mut stack);
    }

    fn visit_children(&mut self, node: Node<'_>, stack: &mut Vec<OwnerFrame>) {
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            self.visit_node(child, stack);
        }
    }

    fn visit_node(&mut self, node: Node<'_>, stack: &mut Vec<OwnerFrame>) {
        if let Some((kind, name)) = owner_frame_for_definition(self.source, node) {
            self.visit_definition(node, stack, OwnerFrame::new(kind, name));
        } else {
            self.visit_children(node, stack);
        }
    }

    fn visit_definition(&mut self, node: Node<'_>, stack: &mut Vec<OwnerFrame>, frame: OwnerFrame) {
        stack.push(frame);
        if let Some(docstring) = definition_docstring(self.source, node) {
            let owner_node_id = self.push_owner_node(node, stack);
            self.push_docstring_region(docstring, stack, &owner_node_id);
        }
        if let Some(body) = node.child_by_field_name("body") {
            self.visit_children(body, stack);
        }
        let _ = stack.pop();
    }

    fn push_owner_node(&mut self, node: Node<'_>, stack: &mut [OwnerFrame]) -> String {
        let current_index = stack.len().saturating_sub(1);
        if let Some(node_id) = stack
            .get(current_index)
            .and_then(|frame| frame.emitted_node_id.clone())
        {
            return node_id;
        }

        let parent = nearest_emitted_owner(stack).unwrap_or_else(|| "n0".to_owned());
        let node_id = self.next_node_id();
        let mut fields = BTreeMap::new();
        if let Some(name) = node.child_by_field_name("name") {
            if let Some(name_text) = helpers::text_for_node(self.source, name) {
                fields.insert("name".to_owned(), name_text);
            }
        }
        self.nodes.push(IrNode {
            id: node_id.clone(),
            tree: TREE_ID.to_owned(),
            kind: node.kind().to_owned(),
            parent: Some(parent.clone()),
            children: Vec::new(),
            fields,
            props: BTreeMap::new(),
            span: source_span(node),
            flags: node_flags(node),
        });
        self.push_child(&parent, &node_id);
        if let Some(frame) = stack.get_mut(current_index) {
            frame.emitted_node_id = Some(node_id.clone());
        }
        node_id
    }

    fn push_docstring_region(
        &mut self,
        string: Node<'_>,
        stack: &[OwnerFrame],
        owner_node_id: &str,
    ) {
        let Some((text, span)) = docstring_content(self.source, string) else {
            return;
        };
        let string_node_id = self.next_node_id();
        self.nodes.push(IrNode {
            id: string_node_id.clone(),
            tree: TREE_ID.to_owned(),
            kind: "string".to_owned(),
            parent: Some(owner_node_id.to_owned()),
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: BTreeMap::new(),
            span: source_span(string),
            flags: node_flags(string),
        });
        self.push_child(owner_node_id, &string_node_id);

        let region_id = self.next_region_id();
        self.regions.push(IrRegion {
            id: region_id,
            kind: "python_docstring".to_owned(),
            scope: vec![
                "python".to_owned(),
                "docstring".to_owned(),
                owner_for(stack).kind,
            ],
            syntax: "python".to_owned(),
            natural_language: None,
            text: text.clone(),
            segments: vec![IrSegment::new(
                0,
                text,
                SegmentOrigin::Source {
                    span,
                    node: string_node_id.clone(),
                },
            )],
            origin_nodes: vec![string_node_id],
            owner: Some(owner_for(stack)),
            attrs: BTreeMap::new(),
            parent_region: None,
        });
    }

    fn push_child(&mut self, parent_id: &str, child_id: &str) {
        if let Some(parent) = self.nodes.iter_mut().find(|node| node.id == parent_id) {
            parent.children.push(child_id.to_owned());
        }
    }

    fn next_node_id(&mut self) -> String {
        let id = format!("n{}", self.next_node);
        self.next_node += 1;
        id
    }

    fn next_region_id(&mut self) -> String {
        let id = format!("r{}", self.next_region);
        self.next_region += 1;
        id
    }
}

#[cfg(test)]
mod tests;
