//! Contract shared by the `make update-snapshots` end-to-end test and the two
//! ignored probes that test runs.
//!
//! The target is deliberately absent from `test` and CI, so a real run is the
//! only thing that proves it still reaches both snapshot-bearing crates. The
//! driver stages a stale snapshot for each crate under [`snapshot_probe_root`],
//! and each crate's probe asserts its accepted value against that staged file.
//! The constants live here so the driver, the probes, and the Makefile's
//! narrowed argument list cannot drift apart.

use std::path::PathBuf;

use stilyagi_test_fixtures::{FixturePathError, repository_root};

/// Scratch directory, under the repository's `target/tmp`, holding both staged
/// probes.
pub const SNAPSHOT_PROBE_ROOT_DIR: &str = "snapshot_update_e2e";

/// Subdirectory `stilyagi-extract`'s probe asserts against.
pub const EXTRACT_PROBE_DIR: &str = "stilyagi-extract";

/// Subdirectory `stilyagi-pyext`'s probe asserts against.
pub const PYEXT_PROBE_DIR: &str = "stilyagi-pyext";

/// Snapshot name, and staged file stem, for the `stilyagi-extract` probe.
pub const EXTRACT_PROBE_SNAPSHOT: &str = "extract_update_probe";

/// Snapshot name, and staged file stem, for the `stilyagi-pyext` probe.
pub const PYEXT_PROBE_SNAPSHOT: &str = "pyext_update_probe";

/// Value the regenerated `stilyagi-extract` snapshot must hold.
pub const EXTRACT_PROBE_ACCEPTED: &str = "extract snapshot accepted";

/// Value the regenerated `stilyagi-pyext` snapshot must hold.
pub const PYEXT_PROBE_ACCEPTED: &str = "pyext snapshot accepted";

/// Value staged before the target runs, which update mode must replace.
pub const SNAPSHOT_PROBE_STALE: &str = "stale spelling";

/// Test-name filter selecting both probes and nothing else.
///
/// The probes share the name in both crates, so one substring filter reaches
/// both through a single Cargo invocation.
pub const SNAPSHOT_PROBE_FILTER: &str = "snapshot_update_probe";

/// Return the scratch root shared by the driver and both probes.
///
/// The root sits in the repository's untracked `target/tmp` directory, so a
/// probe run never touches a tracked snapshot. Deriving it from the fixture
/// crate's compiled-in manifest directory lets both sides agree without
/// reading the process environment at run time.
///
/// # Errors
///
/// Returns [`FixturePathError`] when the crate layout does not sit under a
/// `crates/` directory inside the repository.
///
/// # Examples
///
/// ```
/// use stilyagi_test_support::snapshot_update::snapshot_probe_root;
///
/// let root = snapshot_probe_root().expect("the helper crate lives under crates/");
/// assert!(root.ends_with("target/tmp/snapshot_update_e2e"));
/// ```
pub fn snapshot_probe_root() -> Result<PathBuf, FixturePathError> {
    repository_root().map(|repository| {
        repository
            .join("target")
            .join("tmp")
            .join(SNAPSHOT_PROBE_ROOT_DIR)
    })
}
