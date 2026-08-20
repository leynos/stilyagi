//! A single documented panic boundary for fixture code that cannot propagate.
//!
//! Most fallible test setup should return `Result` and let the test body
//! unwrap, because a fixture failure is a broken test rather than a test
//! verdict. Some contexts cannot do that: a `proptest` strategy combinator
//! chain has type `impl Strategy<Value = T>` with nowhere to put an error, and
//! the closures inside `prop_map` cannot use `?` either.
//!
//! Rather than scatter an anonymous `panic!` through every such site, those
//! contexts funnel through [`ExpectValid`]. One named, explained boundary is
//! auditable; twenty inline panics are not.
//!
//! # Scope and re-use policy
//!
//! Use [`ExpectValid`] **only** where an error genuinely cannot be propagated:
//!
//! - `proptest` strategy constructors and `prop_map` closures;
//! - fixture builders used by `proptest!` bodies (including helpers also
//!   exercised by deterministic tests);
//! - shared assertion helpers with no `Result`-compatible contract. Mark the
//!   helper `#[track_caller]` so failures name the calling test.
//!
//! Do not use it to avoid threading a `Result` through an ordinary fixture. If
//! the helper can return `Result`, it must: callers unwrap in the test body,
//! where a panic is the test verdict and the Whitaker suite permits it.
//!
//! This trait lives here, in the workspace's dependency-free test crate, so
//! that both `stilyagi-ir` and the extraction crates can use it without
//! forming a dependency cycle through `stilyagi-test-support`.
//!
//! # Relationship to the `must_ok!` and `must_some!` macros
//!
//! `crates/stilyagi-markdown/src/tests.rs` and
//! `crates/stilyagi-pyext/src/bridge_bdd.rs` each define `must_ok!` and
//! `must_some!`. Those remain the right tool inside a test body, where a macro
//! expands in place and clippy's `allow-expect-in-tests` already applies.
//! [`ExpectValid`] covers the case they cannot: helper and fixture code that
//! sits *outside* a test body, which the Whitaker suite treats as production.
//! Both spellings report the caller's line — the macros because they expand
//! there, this trait because its methods are `#[track_caller]`.
//!
//! # Examples
//!
//! ```
//! use stilyagi_test_fixtures::ExpectValid;
//!
//! let parsed: Result<u32, _> = "12".parse::<u32>();
//! assert_eq!(parsed.expect_valid("segment offset"), 12);
//!
//! assert_eq!(Some("alpha").expect_valid("region text"), "alpha");
//! ```
//!
//! A malformed fixture names itself in the panic message:
//!
//! ```should_panic(expected = "invalid test fixture: segment offset")
//! use stilyagi_test_fixtures::ExpectValid;
//!
//! let missing: Option<u32> = None;
//! let _ = missing.expect_valid("segment offset");
//! ```
//!
//! The error-bearing branch preserves both the fixture context and the source
//! error:
//!
//! ```should_panic(expected = "invalid test fixture: segment offset: invalid digit found in string")
//! use stilyagi_test_fixtures::ExpectValid;
//!
//! let malformed: Result<u32, _> = "not a number".parse();
//! let _ = malformed.expect_valid("segment offset");
//! ```

use core::fmt::Display;

/// Unwrap a fallible fixture value where no error channel exists.
///
/// Implemented for [`Result`] and [`Option`] so that both fallible
/// constructors and partial lookups share one panic message shape.
pub trait ExpectValid {
    /// The value carried when the fixture input is valid.
    type Valid;

    /// Return the valid value, describing the fixture with `context` on
    /// failure.
    ///
    /// `context` should name the fixture input, not restate the failure — the
    /// underlying error is appended automatically where one exists.
    ///
    /// # Panics
    ///
    /// Panics when the receiver carries no valid value. This is the boundary's
    /// entire purpose: a malformed fixture is a defect in the test suite, and
    /// failing loudly at construction beats generating misleading cases.
    ///
    /// The panic is attributed to the caller, so a failure points at the
    /// fixture that is wrong rather than at this trait.
    #[must_use]
    #[track_caller]
    fn expect_valid(self, context: &str) -> Self::Valid;
}

impl<T, E: Display> ExpectValid for Result<T, E> {
    type Valid = T;

    #[track_caller]
    fn expect_valid(self, context: &str) -> T {
        match self {
            Ok(value) => value,
            Err(error) => panic!("invalid test fixture: {context}: {error}"),
        }
    }
}

impl<T> ExpectValid for Option<T> {
    type Valid = T;

    #[track_caller]
    fn expect_valid(self, context: &str) -> T {
        // A divergent `let`-`else` rather than a `match`, because clippy's
        // `option_if_let_else` rejects the two-arm form and the `unwrap_or_else`
        // form it would otherwise suggest is what Whitaker's
        // `no_unwrap_or_else_panic` forbids.
        let Some(value) = self else {
            panic!("invalid test fixture: {context}");
        };
        value
    }
}

#[cfg(test)]
mod tests {
    //! Tests for panic diagnostics emitted by [`super::ExpectValid`].

    use std::panic::{self, AssertUnwindSafe};
    use std::sync::{Arc, LazyLock, Mutex};

    use super::ExpectValid;

    static PANIC_HOOK_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

    #[test]
    fn option_failure_reports_the_fixture_call_site() {
        let _panic_hook_lock = PANIC_HOOK_LOCK
            .lock()
            .expect("panic hook lock must not be poisoned");
        let panic_location = Arc::new(Mutex::new(None));
        let captured_location = Arc::clone(&panic_location);
        let previous_hook = panic::take_hook();

        panic::set_hook(Box::new(move |panic_info| {
            let location = panic_info
                .location()
                .map(|location| (location.file().to_owned(), location.line()));
            *captured_location
                .lock()
                .expect("panic location lock must not be poisoned") = location;
        }));

        let expected_line = line!() + 3;
        let panic_result = panic::catch_unwind(AssertUnwindSafe(|| {
            let missing: Option<u8> = None;
            let _fixture_value = missing.expect_valid("caller fixture");
        }));

        panic::set_hook(previous_hook);
        assert!(panic_result.is_err(), "missing fixture should panic");

        let actual_location = panic_location
            .lock()
            .expect("panic location lock must not be poisoned")
            .take()
            .expect("panic hook must record a location");
        assert_eq!(actual_location.0, file!());
        assert_eq!(actual_location.1, expected_line);
    }

    /// A shared assertion helper in the shape the scope policy prescribes:
    /// marked `#[track_caller]` so the diagnostics it funnels through
    /// [`super::ExpectValid`] name the calling test rather than this body.
    #[track_caller]
    fn assert_shared_fixture() {
        let missing: Option<u8> = None;
        let _fixture_value = missing.expect_valid("shared assertion helper");
    }

    #[test]
    fn shared_helper_attributes_the_panic_to_the_calling_test() {
        let _panic_hook_lock = PANIC_HOOK_LOCK
            .lock()
            .expect("panic hook lock must not be poisoned");
        let panic_location = Arc::new(Mutex::new(None));
        let captured_location = Arc::clone(&panic_location);
        let previous_hook = panic::take_hook();

        panic::set_hook(Box::new(move |panic_info| {
            let location = panic_info
                .location()
                .map(|location| (location.file().to_owned(), location.line()));
            *captured_location
                .lock()
                .expect("panic location lock must not be poisoned") = location;
        }));

        let expected_line = line!() + 2;
        let panic_result = panic::catch_unwind(AssertUnwindSafe(|| {
            assert_shared_fixture();
        }));

        panic::set_hook(previous_hook);
        assert!(panic_result.is_err(), "missing fixture should panic");

        let actual_location = panic_location
            .lock()
            .expect("panic location lock must not be poisoned")
            .take()
            .expect("panic hook must record a location");
        assert_eq!(actual_location.0, file!());
        assert_eq!(actual_location.1, expected_line);
    }
}
