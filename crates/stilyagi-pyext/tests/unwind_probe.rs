//! Unwind probe: panics must unwind through the extension under the
//! development codegen backend.
//!
//! The development build standard may select the Cranelift backend for the
//! `dev` and `test` profiles. Cranelift's unwinding support has failed on some
//! nightlies, and a green suite does not prove otherwise here because no other
//! test panics through `PyO3` or a spawned thread. `PyO3` wraps every
//! `#[pyfunction]` entry in `catch_unwind` and converts a panic into
//! `PanicException`; a backend that cannot unwind aborts the interpreter
//! instead. One successful panic test is not sufficient evidence, so this probe
//! covers each path separately: the `PyO3` trampoline, a bare `catch_unwind`, a
//! panic in a spawned thread, a panic in a thread spawned from detached Python
//! state, and `should_panic`.

use std::{
    ffi::CString,
    panic::{AssertUnwindSafe, catch_unwind},
    thread,
};

use pyo3::{prelude::*, types::PyDict, wrap_pyfunction};

const MARKER: &str = "unwind-probe-marker";

/// Panic on purpose so the `PyO3` trampoline has something to catch.
#[pyfunction]
fn panics_on_purpose() {
    panic!("{MARKER}");
}

/// Panic in a spawned thread while Python state is detached.
#[pyfunction]
fn panics_in_detached_thread(py: Python<'_>) -> bool {
    py.detach(|| thread::spawn(|| panic!("{MARKER}")).join().is_err())
}

#[test]
fn pyfunction_panic_surfaces_as_panic_exception() {
    Python::attach(|py| {
        let probe = wrap_pyfunction!(panics_on_purpose, py)
            .expect("expected the probe function to be created");
        let globals = PyDict::new(py);
        globals
            .set_item("panics_on_purpose", probe)
            .expect("expected the probe to be bound in the globals");

        // Catch it in Python: a PanicException that crosses back into Rust as
        // a `PyErr` is resumed as a panic by design, which would end the test
        // for a reason that has nothing to do with the backend.
        let code = CString::new(concat!(
            "try:\n",
            "    panics_on_purpose()\n",
            "except BaseException as raised:\n",
            "    outcome = type(raised).__name__ + ':' + str(raised)\n",
        ))
        .expect("expected the probe script to hold no NUL byte");
        py.run(&code, Some(&globals), None)
            .expect("expected the probe to run to completion");

        let outcome = globals
            .get_item("outcome")
            .expect("expected the globals to be readable")
            .expect("expected the panic to have been caught")
            .extract::<String>()
            .expect("expected the outcome to be a string");
        assert_eq!(outcome, format!("PanicException:{MARKER}"));
    });
}

#[test]
fn bare_catch_unwind_catches_a_panic() {
    let outcome = catch_unwind(AssertUnwindSafe(|| panic!("{MARKER}")));

    let payload = outcome.expect_err("expected catch_unwind to return the panic");
    let message = payload
        .downcast_ref::<String>()
        .map(String::as_str)
        .or_else(|| payload.downcast_ref::<&str>().copied());
    assert_eq!(message, Some(MARKER));
}

#[test]
fn spawned_thread_panic_is_reported_by_join() {
    let outcome = thread::spawn(|| panic!("{MARKER}")).join();

    assert!(outcome.is_err());
}

#[test]
fn detached_thread_panic_is_reported_by_join() {
    Python::attach(|py| {
        let probe = wrap_pyfunction!(panics_in_detached_thread, py)
            .expect("expected the probe function to be created");
        let reported = probe
            .call0()
            .expect("expected the detached-thread probe to return")
            .extract::<bool>()
            .expect("expected a bool from the probe");
        assert!(reported);
    });
}

#[test]
#[should_panic(expected = "unwind-probe-marker")]
fn should_panic_observes_the_panic_message() {
    panic!("{MARKER}");
}
