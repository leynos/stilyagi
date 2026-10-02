"""Detector-integration tests for the duplication gate.

Unlike the CLI tests, these invoke the pinned ``nose`` binary itself: one test
runs the checked-in gate through its real command boundary, and the other
plants a verbatim copy and asserts the detector's normalized report names both
duplicated functions.
"""

import dataclasses as dc
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke the pinned, repository-owned binary.
import sys
import textwrap
import typing as typ

import pytest
from duplication_gate_test_support import (
    REPOSITORY_ROOT,
    detector,
    gate_environment,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


class TestRealDetectorIntegration:
    """The pinned detector reached through the gate's own boundaries."""

    def test_real_check_cli_passes(self) -> None:
        """The checked-in gate runs successfully through its real CLI boundary."""
        settings = detector.load_settings(REPOSITORY_ROOT / "pyproject.toml")
        try:
            detector.resolve_binary(settings)
        except detector.GateExecutionError as error:  # pragma: no cover
            pytest.skip(str(error))
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed repository gate command.
            [
                sys.executable,
                str(REPOSITORY_ROOT / "scripts" / "duplication_gate.py"),
                "check",
            ],
            cwd=REPOSITORY_ROOT,
            env=gate_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "duplication gate passed" in result.stdout, (
            "Real check invocation must report its successful gate result."
        )

    def test_reports_a_planted_verbatim_copy(self, tmp_path: Path) -> None:
        """The pinned detector reports a planted copy through normalization."""
        settings = detector.load_settings(REPOSITORY_ROOT / "pyproject.toml")
        try:
            binary = detector.resolve_binary(settings)
        except detector.GateExecutionError as error:  # pragma: no cover
            pytest.skip(str(error))
        body = textwrap.dedent(
            """\
            def NAME(items):
                total = 0.0
                for item in items:
                    price = item["price"] * item["quantity"]
                    if item.get("taxable"):
                        price *= 1.2
                    if item.get("discount"):
                        price -= item["discount"]
                    total += price
                if total < 0:
                    total = 0.0
                return round(total, 2)
            """
        )
        workspace = tmp_path
        (workspace / "mod.py").write_text(
            body.replace("NAME", "first_total")
            + "\n\n"
            + body.replace("NAME", "second_total"),
            encoding="utf-8",
        )
        command = detector.build_command(
            binary, dc.replace(settings, roots=(".",), min_size=8)
        )
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - pinned, repository-owned binary.
            command,
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        findings = detector.normalize_findings(json.loads(result.stdout))
        assert findings, "The planted copy must be reported."
        assert any(
            {location.name for location in finding.locations}
            == {"first_total", "second_total"}
            for finding in findings
        ), "The planted copy must name both duplicated functions."
