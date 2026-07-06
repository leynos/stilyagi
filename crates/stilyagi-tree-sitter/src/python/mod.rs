//! Python docstring extraction backed by `tree-sitter-python`.

mod helpers;
mod observe;
mod owner;
mod support;
mod suppressions;
pub(super) mod types;

use std::collections::{BTreeMap, HashMap};

use stilyagi_ir::{
    DocumentMetadata, IrDocument, IrError, IrNode, IrRegion, IrSegment, IrTree, NodeFlags,
    SegmentOrigin, SourceIdentity,
};
use tree_sitter::Node;

use helpers::{
    collect_error_nodes, definition_docstring, docstring_content, module_docstring,
    nearest_emitted_owner, node_flags, owner_frame_for_definition, source_span,
};
use observe::{record_extraction_outcome, record_fatal_error};
use owner::{OwnerFrame, owner_for};
use support::{parse_python, python_producer, validate_ir_consistency};
use suppressions::collect_comment_suppressions;
use types::{NodeId, NodeKind};

const TREE_ID: &str = "t0";

/// Maximum concrete-syntax-tree depth walked during docstring extraction.
///
/// Real Python source never nests declarations this deeply, but tree-sitter
/// builds arbitrarily deep trees from adversarial or generated input. Capping
/// the recursive descent keeps stack usage bounded and records a recoverable
/// error instead of overflowing, matching the partial-extraction contract used
/// for other malformed input.
const MAX_TRAVERSAL_DEPTH: usize = 256;

/// Fatal failure while building Python docstring IR.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PythonExtractError {
    /// The Python grammar failed to load into the parser.
    GrammarLoad,
    /// tree-sitter returned no parse tree for the source.
    NoParseTree,
}

impl PythonExtractError {
    /// Stable, low-cardinality category label for logs and metrics.
    const fn category(self) -> &'static str {
        match self {
            Self::GrammarLoad => "grammar_load",
            Self::NoParseTree => "no_parse_tree",
        }
    }
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
#[tracing::instrument(
    name = "python_docstring_extraction",
    skip(source, identity),
    fields(syntax = "python", source_len = source.len())
)]
pub fn python_docstring_ir_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<IrDocument, PythonExtractError> {
    metrics::counter!("stilyagi_python_extraction_documents_total").increment(1);
    let tree = parse_python(source).inspect_err(|error| record_fatal_error(*error))?;
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
        root: root_node_id().into(),
    });

    let mut builder = PythonIrBuilder::new(source);
    builder.push_module_root(root);
    builder.push_recovery_errors(root);
    let (suppressions, suppression_errors) = builder.visit_module(root);

    document.nodes = builder.nodes;
    document.regions = builder.regions;
    document.suppressions = suppressions;
    document.errors = builder.errors;
    document.errors.extend(suppression_errors);
    validate_ir_consistency(&document, source);
    record_extraction_outcome(&document);
    Ok(document)
}

/// Mutable state threaded through the recursive descent: the owner-frame stack
/// and the current concrete-syntax-tree depth used to bound recursion.
struct WalkContext<'frames> {
    stack: &'frames mut Vec<OwnerFrame>,
    depth: usize,
}

struct PythonIrBuilder<'source> {
    source: &'source str,
    next_node: usize,
    next_region: usize,
    nodes: Vec<IrNode>,
    // Node id -> index into `nodes` for O(1) parent lookup during child
    // attachment, avoiding a linear scan of `nodes` on every emit.
    node_positions: HashMap<String, usize>,
    regions: Vec<IrRegion>,
    errors: Vec<IrError>,
}

impl<'source> PythonIrBuilder<'source> {
    fn new(source: &'source str) -> Self {
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

    fn push_module_root(&mut self, root: Node<'_>) {
        let node_id = self.next_node_id();
        debug_assert_eq!(node_id.as_str(), root_node_id().as_str());
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

    fn visit_module(&mut self, root: Node<'_>) -> (Vec<stilyagi_ir::IrSuppression>, Vec<IrError>) {
        let mut stack = Vec::new();
        if let Some(docstring) = module_docstring(self.source, root) {
            self.push_docstring_region(docstring, &stack, &root_node_id());
        }
        let mut context = WalkContext {
            stack: &mut stack,
            depth: 0,
        };
        self.visit_children(root, &mut context);
        collect_comment_suppressions(self, root)
    }

    fn visit_children(&mut self, node: Node<'_>, context: &mut WalkContext<'_>) {
        if context.depth >= MAX_TRAVERSAL_DEPTH {
            self.record_depth_limit(node);
            return;
        }
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            context.depth += 1;
            self.visit_node(child, context);
            context.depth -= 1;
        }
    }

    fn visit_node(&mut self, node: Node<'_>, context: &mut WalkContext<'_>) {
        if let Some((kind, name)) = owner_frame_for_definition(self.source, node) {
            self.visit_definition(node, context, OwnerFrame::new(kind, name));
        } else {
            self.visit_children(node, context);
        }
    }

    fn visit_definition(
        &mut self,
        node: Node<'_>,
        context: &mut WalkContext<'_>,
        frame: OwnerFrame,
    ) {
        context.stack.push(frame);
        if let Some(docstring) = definition_docstring(self.source, node) {
            let owner_node_id = self.push_owner_node(node, context.stack);
            self.push_docstring_region(docstring, context.stack, &owner_node_id);
        }
        if let Some(body) = node.child_by_field_name("body") {
            self.visit_children(body, context);
        }
        let _ = context.stack.pop();
    }

    /// Record a recoverable error when the traversal reaches the maximum depth.
    ///
    /// Bounding the recursive descent prevents stack overflow on deeply nested
    /// or adversarial input; the untraversed subtree is reported through the IR
    /// `errors` list rather than silently dropped.
    fn record_depth_limit(&mut self, node: Node<'_>) {
        let span = source_span(node);
        tracing::warn!(
            byte_start = span.byte_start,
            byte_end = span.byte_end,
            max_depth = MAX_TRAVERSAL_DEPTH,
            "python docstring traversal stopped at the maximum tree depth"
        );
        self.errors.push(IrError {
            code: "python-traversal-depth-limit".to_owned(),
            message: format!(
                "stopped Python docstring traversal at the maximum depth of \
                 {MAX_TRAVERSAL_DEPTH} at bytes {}..{}",
                span.byte_start, span.byte_end
            ),
            span: Some(span),
        });
    }

    fn push_owner_node(&mut self, node: Node<'_>, stack: &mut [OwnerFrame]) -> NodeId {
        let current_index = stack.len().saturating_sub(1);
        if let Some(node_id) = stack
            .get(current_index)
            .and_then(|frame| frame.emitted_node_id.clone())
        {
            return node_id;
        }

        let parent = nearest_emitted_owner(stack).unwrap_or_else(root_node_id);
        let node_id = self.next_node_id();
        let mut fields = BTreeMap::new();
        if let Some(name) = node.child_by_field_name("name") {
            if let Some(name_text) = helpers::text_for_node(self.source, name) {
                fields.insert("name".to_owned(), name_text);
            }
        }
        self.push_node(IrNode {
            id: node_id.clone().into(),
            tree: TREE_ID.to_owned(),
            kind: NodeKind(node.kind()).as_str().to_owned(),
            parent: Some(parent.clone().into()),
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
        owner_node_id: &NodeId,
    ) {
        let Some((text, span)) = docstring_content(self.source, string) else {
            return;
        };
        let string_node_id = self.next_node_id();
        self.push_node(IrNode {
            id: string_node_id.clone().into(),
            tree: TREE_ID.to_owned(),
            kind: NodeKind("string").as_str().to_owned(),
            parent: Some(owner_node_id.clone().into()),
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: BTreeMap::new(),
            span: source_span(string),
            flags: node_flags(string),
        });
        self.push_child(owner_node_id, &string_node_id);

        let owner = owner_for(stack);
        tracing::trace!(
            owner_kind = owner.kind.as_str(),
            "emitting python docstring region"
        );
        let region_id = self.next_region_id();
        self.regions.push(IrRegion {
            id: region_id,
            kind: "python_docstring".to_owned(),
            scope: vec![
                "python".to_owned(),
                "docstring".to_owned(),
                owner.kind.clone(),
            ],
            syntax: "python".to_owned(),
            natural_language: None,
            text: text.clone(),
            segments: vec![IrSegment::new(
                0,
                text,
                SegmentOrigin::Source {
                    span,
                    node: string_node_id.clone().into(),
                },
            )],
            origin_nodes: vec![string_node_id.into()],
            owner: Some(owner),
            attrs: BTreeMap::new(),
            parent_region: None,
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

fn root_node_id() -> NodeId {
    NodeId("n0".to_owned())
}

#[cfg(test)]
mod tests;
