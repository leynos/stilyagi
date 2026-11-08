//! Bounded Python definition traversal for the docstring IR builder.
//!
//! Builder state stays private in the parent module; this child only owns
//! recursive descent and reports its depth limit through the existing IR.

use stilyagi_ir::IrError;
use tree_sitter::Node;

use super::{
    MAX_TRAVERSAL_DEPTH,
    PythonIrBuilder,
    WalkContext,
    helpers::{definition_docstring, owner_frame_for_definition, source_span},
    owner::OwnerFrame,
};

impl PythonIrBuilder<'_> {
    /// Walk the named children of `node`, recording a recoverable error when
    /// the depth limit is reached.
    pub(super) fn visit_children(&mut self, node: Node<'_>, context: &mut WalkContext<'_>) {
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

    /// Dispatch a node to definition handling or recurse into its children.
    fn visit_node(&mut self, node: Node<'_>, context: &mut WalkContext<'_>) {
        if let Some((kind, name)) = owner_frame_for_definition(self.source, node) {
            self.visit_definition(node, context, OwnerFrame::new(kind, name));
        } else {
            self.visit_children(node, context);
        }
    }

    /// Push an owner frame, emit its docstring region when present, then walk
    /// the body.
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
                concat!(
                    "stopped Python docstring traversal at the maximum depth of {} ",
                    "at bytes {}..{}",
                ),
                MAX_TRAVERSAL_DEPTH, span.byte_start, span.byte_end
            ),
            span: Some(span),
        });
    }
}
