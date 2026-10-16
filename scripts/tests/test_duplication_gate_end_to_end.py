"""End-to-end blocking tests for the duplication gate.

Every other blocking test substitutes a stub report or calls the detector
without the gate, so none of them shows that a genuine duplicate reaches
``check`` and fails the build. These do, using the pinned binary.
"""

import textwrap
import typing as typ

import pytest
from duplication_gate_test_support import (
    REPOSITORY_ROOT,
    copied_gate_workspace,
    detector,
    gate_environment,
    run_gate_command,
)

if typ.TYPE_CHECKING:
    import subprocess
    from pathlib import Path


class TestEndToEndBlocking:
    """The real detector driving the real `check` command."""

    DUPLICATE_BODY = textwrap.dedent(
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

    def _planted_workspace(self, tmp_path: Path, *, allow: str = "") -> Path:
        """Build a gate workspace whose package holds one verbatim duplicate."""
        workspace, _script = copied_gate_workspace(tmp_path)
        package = workspace / "planted"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "mod.py").write_text(
            self.DUPLICATE_BODY.replace("NAME", "first_total")
            + "\n\n"
            + self.DUPLICATE_BODY.replace("NAME", "second_total"),
            encoding="utf-8",
        )
        (workspace / "pyproject.toml").write_text(
            textwrap.dedent(
                """\
                [project]
                name = "gate-test"
                version = "0"

                [tool.nose]
                version = "0.20.0"
                roots = ["planted"]
                mode = "syntax,semantic,near"
                min-size = 8
                surface = "all"
                top = 30
                """
            )
            + allow,
            encoding="utf-8",
        )
        return workspace

    def _run_check(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        """Run the copied gate's real `check` against the pinned detector."""
        settings = detector.load_settings(REPOSITORY_ROOT / "pyproject.toml")
        try:
            binary = detector.resolve_binary(settings)
        except detector.GateExecutionError as error:  # pragma: no cover
            pytest.skip(str(error))
        return run_gate_command(
            workspace / "scripts" / "duplication_gate.py",
            "check",
            environment=gate_environment(NOSE_BIN=binary),
        )

    def test_planted_duplicate_blocks_the_gate(self, tmp_path: Path) -> None:
        """A genuine duplicate fails `check` and names both copies."""
        result = self._run_check(self._planted_workspace(tmp_path))

        assert result.returncode == 1, (
            f"A planted duplicate must fail the gate.\n{result.stdout}{result.stderr}"
        )
        assert "planted/mod.py" in result.stdout, (
            "The report must locate the duplicated file."
        )
        assert "make duplication-allow" in result.stdout, (
            "A blocking report must show how to record a reasoned exception."
        )

    def test_reasoned_exception_unblocks_the_planted_duplicate(
        self, tmp_path: Path
    ) -> None:
        """The same duplicate passes once a reasoned allow entry covers it."""
        allow = textwrap.dedent(
            """
            [[tool.duplication_gate.allow]]
            unit = "planted/mod.py"
            reason = "Planted fixture proving the gate blocks and allows."
            """
        )
        result = self._run_check(self._planted_workspace(tmp_path, allow=allow))

        assert result.returncode == 0, (
            f"A covered duplicate must pass.\n{result.stdout}{result.stderr}"
        )
        assert "duplication gate passed" in result.stdout, (
            "The gate must report its successful result."
        )
