//! Shared state and grouping helpers for Rust doc-comment extraction.

use stilyagi_ir::{IrSegment, SegmentOrigin, SyntheticReason};
use tree_sitter::Node;

use super::helpers::DocCommentFlavour;
use super::owner::OwnerFrame;
use super::types::NodeId;

/// Comment node awaiting emission into an owner-aware doc-comment region.
#[derive(Debug)]
pub(super) struct DocCommentEntry<'source> {
    /// Comment node this entry was derived from.
    pub(super) node: Node<'source>,
    /// Documentation-comment flavour of the node.
    pub(super) flavour: DocCommentFlavour,
    /// Comment text with the documentation marker removed.
    pub(super) content: String,
    /// Source span of `content` within the original source.
    pub(super) content_span: stilyagi_ir::SourceSpan,
}

/// Group of adjacent documentation comments that form one emitted region.
#[derive(Debug, Default)]
pub(super) struct DocCommentGroup<'source> {
    /// Adjacent entries that make up this group, in source order.
    pub(super) entries: Vec<DocCommentEntry<'source>>,
}

impl<'source> DocCommentGroup<'source> {
    /// Create a group containing a single entry.
    pub(super) fn new(entry: DocCommentEntry<'source>) -> Self {
        Self {
            entries: vec![entry],
        }
    }

    /// Append an entry to the group.
    pub(super) fn push(&mut self, entry: DocCommentEntry<'source>) {
        self.entries.push(entry);
    }

    /// Return whether the group's first entry is a line comment.
    pub(super) fn is_line(&self) -> bool {
        self.entries
            .first()
            .is_some_and(|entry| entry.flavour.is_line())
    }
}

/// Mutable text and segment buffers for one doc-comment region.
pub(super) struct DocCommentRegionParts<'text> {
    /// Accumulated region text.
    pub(super) text: &'text mut String,
    /// Segments describing how `text` was assembled.
    pub(super) segments: &'text mut Vec<IrSegment>,
}

impl DocCommentRegionParts<'_> {
    /// Append source-backed text and record its segment.
    pub(super) fn push_source_segment(
        &mut self,
        segment_text: &str,
        span: stilyagi_ir::SourceSpan,
        node_id: NodeId,
    ) {
        let text_start = self.text.len();
        self.text.push_str(segment_text);
        self.segments.push(IrSegment::new(
            text_start,
            segment_text,
            SegmentOrigin::Source {
                span,
                node: node_id.into(),
            },
        ));
    }

    /// Append synthetic text and record it as a softbreak space.
    pub(super) fn push_synthetic_segment(&mut self, value: &str) {
        let text_start = self.text.len();
        self.text.push_str(value);
        self.segments.push(IrSegment::new(
            text_start,
            value,
            SegmentOrigin::Synthetic {
                reason: SyntheticReason::SoftbreakSpace,
            },
        ));
    }
}

/// Borrowed traversal state passed while handling a non-doc child.
pub(super) struct NonDocCommentState<'stack, 'source> {
    /// Owner frames for the enclosing items.
    pub(super) stack: &'stack mut Vec<OwnerFrame>,
    /// Outer doc-comment groups awaiting an owner.
    pub(super) pending_outer: &'stack mut Vec<DocCommentGroup<'source>>,
    /// Inner doc-comment groups awaiting an owner.
    pub(super) pending_inner: &'stack mut Vec<DocCommentGroup<'source>>,
    /// Current traversal depth.
    pub(super) depth: usize,
}

/// Add an entry to `groups`, merging it with the previous line group when
/// adjacent.
pub(super) fn push_group<'source>(
    source: &str,
    groups: &mut Vec<DocCommentGroup<'source>>,
    entry: DocCommentEntry<'source>,
) {
    let should_merge = groups.last_mut().is_some_and(|last| {
        last.is_line()
            && entry.flavour.is_line()
            && last.entries.last().is_some_and(|last_entry| {
                super::helpers::line_comments_can_merge(
                    source,
                    last_entry.content_span.byte_end,
                    entry.node.start_byte(),
                )
            })
    });
    if should_merge && let Some(last) = groups.last_mut() {
        last.push(entry);
        return;
    }
    groups.push(DocCommentGroup::new(entry));
}
