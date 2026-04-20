//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::prelude::*;
use pyo3::types::PyModule;
use stilyagi_core::smoke_hello;

/// Return a simple Rust-side greeting for smoke-testing the extension bridge.
#[pyfunction]
const fn hello() -> &'static str {
    smoke_hello()
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::hello;
    use rstest::{fixture, rstest};
    use rstest_bdd_macros::{given, scenario, then, when};

    struct BridgeState {
        bridge_greeting: Option<&'static str>,
        core_greeting: Option<&'static str>,
    }

    #[fixture]
    fn bridge_state() -> BridgeState {
        BridgeState {
            bridge_greeting: None,
            core_greeting: None,
        }
    }

    #[rstest]
    fn hello_delegates_to_the_core_smoke_greeting() {
        assert_eq!(hello(), stilyagi_core::smoke_hello());
    }

    #[rstest]
    #[case("hello from Python")]
    fn hello_is_not_the_legacy_python_fallback(#[case] legacy_fallback: &str) {
        assert_ne!(hello(), legacy_fallback);
    }

    #[given("the bridge can call the shared smoke greeting")]
    fn bridge_can_call_the_shared_smoke_greeting(bridge_state: &mut BridgeState) {
        bridge_state.core_greeting = Some(stilyagi_core::smoke_hello());
    }

    #[when("the bridge produces a hello greeting")]
    fn bridge_produces_a_hello_greeting(bridge_state: &mut BridgeState) {
        bridge_state.bridge_greeting = Some(hello());
    }

    #[then("the greeting matches the core crate greeting")]
    fn greeting_matches_the_core_crate_greeting(bridge_state: &BridgeState) {
        assert_eq!(bridge_state.bridge_greeting, bridge_state.core_greeting);
    }

    #[then("the greeting is not the legacy Python fallback")]
    fn greeting_is_not_the_legacy_python_fallback(bridge_state: &BridgeState) {
        assert_ne!(bridge_state.bridge_greeting, Some("hello from Python"));
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge delegates the smoke greeting to the core crate"
    )]
    fn bridge_delegates_the_smoke_greeting_to_the_core_crate(bridge_state: BridgeState) {
        let _ = bridge_state;
    }

    #[scenario(
        path = "tests/features/bridge_structure.feature",
        name = "Bridge greeting is not the legacy Python fallback"
    )]
    fn bridge_greeting_is_not_the_legacy_python_fallback(bridge_state: BridgeState) {
        let _ = bridge_state;
    }
}
