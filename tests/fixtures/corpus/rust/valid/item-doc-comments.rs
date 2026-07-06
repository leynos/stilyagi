//! Crate-level documentation comment for the shared Stilyagi corpus.

// stilyagi: ignore-next terminology
/// Item-level documentation comment used by later Rust extraction slices.
pub struct FixtureExample;

// stilyagi: disable terminology
impl FixtureExample {
    /// Method documentation comment with extractable prose.
    pub fn documented_value(&self) -> &'static str {
        "documented"
    }
}

// stilyagi: enable terminology
// stilyagi: ignore-file
// stilyagi: disable
/// Function documentation comment after a suppression marker.
pub fn fixture_function() {}
