//! Intermediate representation (IR) crate boundary marker and shared helpers.
//!
//! This crate currently exposes the future IR boundary marker and the
//! [`line_index_for`] helper shared by internal fixture builders. Test-only
//! golden IR DTOs live in `stilyagi-test-support`, so this crate does not
//! expose helper shapes as production API.

mod canonical_json;

pub use canonical_json::line_index_for;

/// Marker type for the future IR crate boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct IrBoundary;

#[cfg(test)]
mod tests {
    use super::IrBoundary;

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn ir_boundary_default_matches_the_marker_value() {
        assert_eq!(IrBoundary::default(), IrBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn ir_boundary_clone_matches_the_original() {
        let boundary = IrBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn ir_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{IrBoundary:?}").contains("IrBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn ir_boundary_is_copy() {
        let original = IrBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }
}
