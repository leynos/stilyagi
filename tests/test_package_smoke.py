"""Smoke tests for the mixed Rust/Python package wiring."""

import importlib

import pytest
import stilyagi

from tests.support.assertions import assert_with_context


def test_hello_uses_rust_extension() -> None:
    """The relocated package should still expose the Rust greeting."""
    importlib.import_module("stilyagi.engine")
    importlib.import_module("stilyagi.model")
    assert_with_context(
        stilyagi.hello() == "hello from Rust",
        "expected stilyagi.hello() == 'hello from Rust'",
    )


def test_legacy_pure_python_fallback_is_not_importable() -> None:
    """The long-lived package surface should not expose ``stilyagi.pure``."""
    with pytest.raises(ModuleNotFoundError, match=r"stilyagi\.pure"):
        importlib.import_module("stilyagi.pure")
