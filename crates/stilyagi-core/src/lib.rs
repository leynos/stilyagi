//! Shared Rust-side core boundaries for the Stilyagi engine.

/// Return the shared Rust greeting used to smoke-test the bridge skeleton.
#[must_use]
pub const fn smoke_hello() -> &'static str {
    "hello from Rust"
}
