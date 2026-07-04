//! Shared state and grouping helpers for Rust doc-comment extraction.

use stilyagi_ir::{IrSegment, SegmentOrigin, SyntheticReason};
use tree_sitter::Node;

use super::helpers::DocCommentFlavor;
use super::owner::OwnerFrame;
use super::types::NodeId;

/// Comment node awaiting emission into an owner-aware doc-comment region.
#[derive(Debug)]
pub(super) struct DocCommentEntry<'source> {
    pub(super) node: Node<'source>,
    pub(super) flavor: DocCommentFlavor,
    pub(super) content: String,
    pub(super) content_span: stilyagi_ir::SourceSpan,
}

/// Group of adjacent documentation comments that form one emitted region.
#[derive(Debug, Default)]
pub(super) struct DocCommentGroup<'source> {
    pub(super) entries: Vec<DocCommentEntry<'source>>,
}

impl<'source> DocCommentGroup<'source> {
    pub(super) fn new(entry: DocCommentEntry<'source>) -> Self {
        Self {
            entries: vec![entry],
        }
    }

    pub(super) fn push(&mut self, entry: DocCommentEntry<'source>) {
        self.entries.push(entry);
    }

    pub(super) fn is_line(&self) -> bool {
        self.entries
            .first()
            .is_some_and(|entry| entry.flavor.is_line())
    }
}

pub(super) struct DocCommentRegionParts<'text> {
    pub(super) text: &'text mut String,
    pub(super) segments: &'text mut Vec<IrSegment>,
}

impl DocCommentRegionParts<'_> {
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

pub(super) struct NonDocCommentState<'stack, 'source> {
    pub(super) stack: &'stack mut Vec<OwnerFrame>,
    pub(super) pending_outer: &'stack mut Vec<DocCommentGroup<'source>>,
    pub(super) pending_inner: &'stack mut Vec<DocCommentGroup<'source>>,
    pub(super) depth: usize,
}

pub(super) fn push_group<'source>(
    source: &str,
    groups: &mut Vec<DocCommentGroup<'source>>,
    entry: DocCommentEntry<'source>,
) {
    let should_merge = groups.last_mut().is_some_and(|last| {
        last.is_line()
            && entry.flavor.is_line()
            && last.entries.last().is_some_and(|last_entry| {
                super::helpers::line_comments_can_merge(
                    source,
                    last_entry.content_span.byte_end,
                    entry.node.start_byte(),
                )
            })
    });
    if should_merge {
        if let Some(last) = groups.last_mut() {
            last.push(entry);
            return;
        }
    }
    groups.push(DocCommentGroup::new(entry));
}
