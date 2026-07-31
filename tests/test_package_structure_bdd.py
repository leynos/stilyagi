"""Behaviour tests for the mixed-package repository skeleton."""

import json
import pathlib
import subprocess  # noqa: S404  # subprocess drives installed-package probes
import sys
import typing as typ

from pytest_bdd import given, scenarios, then, when

scenarios("../features/stilyagi_package_structure.feature")

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


class PythonCommandResult(typ.TypedDict):
    """Captured result for a subprocess-based package probe."""

    returncode: int
    stdout: str
    stderr: str


class PackageProbeState(typ.TypedDict):
    """Per-scenario subprocess results."""

    boundary_probe: PythonCommandResult | None
    fallback_probe: PythonCommandResult | None


class BuildSpineState(typ.TypedDict):
    """Per-scenario build-spine file contents."""

    makefile: str
    workflow: str


@given("the built Stilyagi package is available", target_fixture="package_probe_state")
def package_probe_state() -> PackageProbeState:
    """Return an empty scenario state."""
    return {"boundary_probe": None, "fallback_probe": None}


@given("the repository build spine is available", target_fixture="build_spine_state")
def build_spine_state() -> BuildSpineState:
    """Read the build-spine files used by the canonical workflows."""
    return {
        "makefile": "",
        "workflow": "",
    }


@when("I inspect the canonical build workflows")
def inspect_canonical_build_workflows(build_spine_state: BuildSpineState) -> None:
    """Inspect Makefile and GitHub Actions workflow wiring."""
    build_spine_state["makefile"] = (REPOSITORY_ROOT / "Makefile").read_text(
        encoding="utf-8",
    )
    build_spine_state["workflow"] = (
        REPOSITORY_ROOT / ".github" / "workflows" / "smoke.yml"
    ).read_text(encoding="utf-8")


@then("make build runs the development smoke check")
def make_build_runs_the_development_smoke_check(
    build_spine_state: BuildSpineState,
) -> None:
    """Confirm the development install path invokes the package smoke helper."""
    assert "$(MAKE) smoke" in build_spine_state["makefile"], (
        "expected '$(MAKE) smoke' in build_spine_state['makef..."
    )
    assert ".venv" in build_spine_state["makefile"], (
        "expected '.venv' in build_spine_state['makefile']"
    )
    assert "-m stilyagi.smoke" in build_spine_state["makefile"], (
        "expected '-m stilyagi.smoke' in build_spine_state['m..."
    )


@then("make release runs the release artefact smoke check")
def make_release_runs_the_release_artefact_smoke_check(
    build_spine_state: BuildSpineState,
) -> None:
    """Confirm the release path smokes the built wheel."""
    assert "release: release-artifact smoke-release" in build_spine_state["makefile"], (
        "expected 'release: release-artifact smoke-release' i..."
    )
    assert ".venv-release-smoke" in build_spine_state["makefile"], (
        "expected '.venv-release-smoke' in build_spine_state[..."
    )


@then("CI uses the canonical Makefile smoke path")
def ci_uses_the_canonical_makefile_smoke_path(
    build_spine_state: BuildSpineState,
) -> None:
    """Confirm CI runs lint/test targets and release wheel smoke coverage."""
    assert "run: make test" in build_spine_state["workflow"], (
        "expected 'run: make test' in build_spine_state['work..."
    )
    assert "release-smoke:" in build_spine_state["workflow"], (
        "expected 'release-smoke:' in build_spine_state['work..."
    )
    assert "run: make release" in build_spine_state["workflow"], (
        "expected 'run: make release' in build_spine_state['w..."
    )
    assert (
        "uv run --group dev maturin build --release"
        not in build_spine_state["workflow"]
    ), "expected 'uv run --group dev maturin build --release..."


@when("I inspect the supported package boundaries")
def inspect_supported_package_boundaries(
    package_probe_state: PackageProbeState,
) -> None:
    """Inspect the supported package surface in a subprocess."""
    package_probe_state["boundary_probe"] = run_python_snippet(
        """
import dataclasses as dc
import json
import stilyagi

document = stilyagi.engine.extract_document("# Heading", stilyagi.model.Syntax.MARKDOWN)
payload = dc.asdict(document)
payload["syntax"] = document.syntax.value
print(json.dumps(payload))
"""
    )


@then("the engine and model packages import successfully")
def engine_and_model_packages_import_successfully(
    package_probe_state: PackageProbeState,
) -> None:
    """Confirm that the supported package boundaries import without errors."""
    boundary_probe = require_result(package_probe_state["boundary_probe"])
    assert boundary_probe["returncode"] == 0, boundary_probe["stderr"]


@then("the package reports a Markdown document extracted by Rust")
def package_reports_a_markdown_document_extracted_by_rust(
    package_probe_state: PackageProbeState,
) -> None:
    """Confirm that the subprocess reports the Rust-backed document payload."""
    boundary_probe = require_result(package_probe_state["boundary_probe"])
    payload = json.loads(boundary_probe["stdout"])
    regions = payload["regions"]
    assert payload["syntax"] == "markdown", "expected payload['syntax'] == 'markdown'"
    assert {"kind": "heading", "text": "Heading"} in regions, (
        "expected extracted Markdown regions to include the heading payload, "
        f"got {regions!r}"
    )


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
    assert fallback_probe["returncode"] != 0, (
        "expected fallback_probe['returncode'] != 0"
    )
    assert "ModuleNotFoundError" in fallback_probe["stderr"], (
        "expected 'ModuleNotFoundError' in fallback_probe['st..."
    )
    assert "stilyagi.pure" in fallback_probe["stderr"], (
        "expected 'stilyagi.pure' in fallback_probe['stderr']"
    )


def run_python_snippet(source: str) -> PythonCommandResult:
    """Run a Python snippet in a subprocess and capture its result."""
    completed_process = subprocess.run(  # noqa: S603  # arguments are fixed test data
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
