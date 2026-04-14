"""Smoke tests for the mixed Rust/Python package wiring."""

import stilyagi


def test_hello_uses_rust_extension() -> None:
    """The development build should expose the Rust greeting."""
    assert stilyagi.hello() == "hello from Rust"
