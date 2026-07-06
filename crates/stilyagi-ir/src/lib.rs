//! Intermediate representation (IR) domain types and shared helpers.
//!
//! The crate owns Stilyagi's stable, source-faithful IR vocabulary. Markdown
//! parsers, `PyO3` bridges, and Python models adapt to these types rather than
//! defining their own logical document contracts.

mod canonical_json;
mod diagnostics;
mod document;
mod region;
mod source_identity;
pub mod suppression;
mod tree;

pub use canonical_json::{content_hash_for, line_index_for};
pub use diagnostics::{IrError, IrSuppression, RangeRole, SuppressionKind};
pub use document::{DocumentMetadata, IrBuildContext, IrDocument, ProducerMetadata};
pub use region::{
    InvalidRegionKind, IrOwner, IrRegion, IrSegment, RegionKind, SegmentOrigin, SyntheticReason,
};
pub use source_identity::SourceIdentity;
pub use suppression::{
    DirectiveError, DirectiveOutcome, DirectiveVerb, ParsedDirective, SuppressionCandidate,
    SuppressionValidationError, is_directive_marker, parse_comment_directive,
    suppressions_from_candidates, validate_suppressions, verb_kind,
};
pub use tree::{IrNode, IrTree, NodeFlags, SourceSpan};

/// Current schema version for Stilyagi IR documents.
pub const SCHEMA_VERSION: &str = "1.1.0";

/// Marker type for the future IR crate boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct IrBoundary;

#[cfg(test)]
mod tests;
