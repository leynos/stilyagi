//! Crate-level documentation comment for the shared Stilyagi corpus.

/// Item-level documentation comment used by later Rust extraction slices.
pub struct FixtureExample;

impl FixtureExample {
    /// Method documentation comment with extractable prose.
    pub fn documented_value(&self) -> &'static str {
        "documented"
    }
}

// stilyagi-disable-next-line terminology
/// Function documentation comment after a suppression marker.
pub fn fixture_function() {}

