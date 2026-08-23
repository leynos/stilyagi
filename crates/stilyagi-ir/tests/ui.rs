//! Compile-time guards for the `sha2` 0.11 migration.
//!
//! `sha2` 0.11 made a source-breaking change that this crate had to work
//! around: `Sha256::finalize()` / `Sha256::digest()` now return
//! `hybrid_array::Array<u8, _>`, which does not implement
//! [`core::fmt::LowerHex`], so `format!("{:x}", digest)` no longer compiles.
//! Digests are therefore rendered through the crate's `to_lower_hex` helper.
//!
//! The trait assertion pins that break without snapshotting compiler diagnostic
//! wording. If a future change reintroduces the pre-0.11 pattern — for example
//! by downgrading `sha2` back to 0.10 — the assertion stops compiling and this
//! test fails, flagging the regression.

use core::fmt::LowerHex;

use sha2::{Sha256, digest::Output};
use static_assertions::assert_not_impl_any;

#[test]
fn sha2_0_11_digest_does_not_implement_lowerhex() {
    assert_not_impl_any!(Output<Sha256>: LowerHex);
}
