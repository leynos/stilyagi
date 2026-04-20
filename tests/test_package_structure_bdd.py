"""Behaviour tests for the mixed-package repository skeleton."""

import json
import subprocess  # noqa: S404
import sys
import typing as typ

from pytest_bdd import given, scenarios, then, when

scenarios("../features/stilyagi_package_structure.feature")


class PythonCommandResult(typ.TypedDict):
    """Captured result for a subprocess-based package probe."""

    returncode: int
    stdout: str
    stderr: str


class PackageProbeState(typ.TypedDict):
    """Per-scenario subprocess results."""

    boundary_probe: PythonCommandResult | None
    fallback_probe: PythonCommandResult | None


@given("the built Stilyagi package is available", target_fixture="package_probe_state")
def package_probe_state() -> PackageProbeState:
    """Return an empty scenario state."""
    return {"boundary_probe": None, "fallback_probe": None}


@when("I inspect the supported package boundaries")
def inspect_supported_package_boundaries(
    package_probe_state: PackageProbeState,
) -> None:
    """Inspect the supported package surface in a subprocess."""
    package_probe_state["boundary_probe"] = run_python_snippet(
        """
import importlib
import json
import stilyagi

importlib.import_module("stilyagi.engine")
importlib.import_module("stilyagi.model")

print(json.dumps({"hello": stilyagi.hello()}))
"""
    )


@then("the engine and model packages import successfully")
def engine_and_model_packages_import_successfully(
    package_probe_state: PackageProbeState,
) -> None:
    """Confirm that the supported package boundaries import without errors."""
    boundary_probe = require_result(package_probe_state["boundary_probe"])
    assert boundary_probe["returncode"] == 0, boundary_probe["stderr"]


@then("the package reports the Rust smoke greeting")
def package_reports_the_rust_smoke_greeting(
    package_probe_state: PackageProbeState,
) -> None:
    """Confirm that the subprocess reports the Rust-backed greeting."""
    boundary_probe = require_result(package_probe_state["boundary_probe"])
    payload = json.loads(boundary_probe["stdout"])
    assert payload["hello"] == "hello from Rust"


@when("I import the legacy pure-Python fallback module")
def import_legacy_pure_python_fallback_module(
    package_probe_state: PackageProbeState,
) -> None:
    """Attempt to import the legacy fallback path in a subprocess."""
    package_probe_state["fallback_probe"] = run_python_snippet(
        """
import importlib

importlib.import_module("stilyagi.pure")
"""
    )


@then("the import fails with ModuleNotFoundError")
def import_fails_with_module_not_found_error(
    package_probe_state: PackageProbeState,
) -> None:
    """Confirm that the legacy fallback module is no longer importable."""
    fallback_probe = require_result(package_probe_state["fallback_probe"])
    assert fallback_probe["returncode"] != 0
    assert "ModuleNotFoundError" in fallback_probe["stderr"]


def run_python_snippet(source: str) -> PythonCommandResult:
    """Run a Python snippet in a subprocess and capture its result."""
    completed_process = subprocess.run(  # noqa: S603
        [sys.executable, "-c", source],
        capture_output=True,
        check=False,
        text=True,
    )
    return {
        "returncode": completed_process.returncode,
        "stdout": completed_process.stdout,
        "stderr": completed_process.stderr,
    }


def require_result(result: PythonCommandResult | None) -> PythonCommandResult:
    """Fail fast if the scenario forgot to populate a subprocess result."""
    assert result is not None, "expected PythonCommandResult but got None"
    return result
