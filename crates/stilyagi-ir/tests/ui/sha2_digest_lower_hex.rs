//! Compile-fail fixture guarding the `sha2` 0.11 `LowerHex` formatting break.

use sha2::{Digest, Sha256};

fn main() {
    let digest = Sha256::digest(b"abc");
    let _ = format!("{digest:x}");
}
