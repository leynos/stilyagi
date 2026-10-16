"""Tests for resolving the pinned detector binary and building its command.

The wrapper discovers the ``nose`` executable, verifies its reported version
against ``[tool.nose] version``, and translates the validated settings into the
``nose query`` argument vector; these tests pin both boundaries.
"""

import dataclasses as dc
import typing as typ

import pytest
from duplication_gate_test_support import (
    detector,
    stub_runner,
    stub_settings,
    write_stub_nose,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from syrupy.assertion import SnapshotAssertion


class TestResolveBinary:
    """Discovery and version verification of the pinned binary."""

    def test_accepts_the_pinned_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A binary reporting the pinned version is accepted."""
        stub = write_stub_nose(tmp_path)
        monkeypatch.setenv("NOSE_BIN", str(stub))
        assert detector.resolve_binary(stub_settings(), runner=stub_runner()) == str(
            stub
        ), "The pinned binary must be returned unchanged."

    def test_rejects_a_version_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A different installed version fails with a remediation hint."""
        stub = write_stub_nose(tmp_path, version="nose 0.19.0")
        monkeypatch.setenv("NOSE_BIN", str(stub))
        with pytest.raises(
            detector.GateExecutionError,
            match=r"reports 'nose 0\.19\.0'.*make install-nose",
        ):
            detector.resolve_binary(
                stub_settings(), runner=stub_runner(version="nose 0.19.0")
            )

    def test_reports_a_missing_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing detector fails with the install remediation."""
        monkeypatch.delenv("NOSE_BIN", raising=False)
        monkeypatch.setattr(detector, "_discover_binary", lambda: None)
        with pytest.raises(detector.GateExecutionError, match="make install-nose"):
            detector.resolve_binary(stub_settings(), runner=stub_runner())

    @pytest.mark.parametrize("at_repo_root", [True, False], ids=["rooted", "path"])
    def test_a_bare_name_prefers_the_root_then_falls_back_to_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        at_repo_root: bool,
    ) -> None:
        """A bare NOSE_BIN keeps root priority, else resolves through PATH."""
        (tmp_path / "repo").mkdir()
        (tmp_path / "bin").mkdir()
        (tmp_path / "empty").mkdir()
        rooted_stub = write_stub_nose(tmp_path / "repo") if at_repo_root else None
        path_stub = write_stub_nose(tmp_path / "bin")
        monkeypatch.setattr(detector, "REPO_ROOT", tmp_path / "repo")
        monkeypatch.setenv("NOSE_BIN", "nose")
        monkeypatch.setenv("PATH", str(tmp_path / "bin"))
        expected = rooted_stub if at_repo_root else path_stub
        assert detector.resolve_binary(stub_settings(), runner=stub_runner()) == str(
            expected
        ), "The repository root must win when present, and PATH must apply when not."

    def test_a_bare_name_missing_everywhere_reports_the_install_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare name found neither at the root nor on PATH fails closed."""
        monkeypatch.setattr(detector, "REPO_ROOT", tmp_path / "repo")
        monkeypatch.setenv("NOSE_BIN", "nose")
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        with pytest.raises(detector.GateExecutionError, match="make install-nose"):
            detector.resolve_binary(stub_settings(), runner=stub_runner())

    def test_relative_path_override_stays_repository_rooted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A path-shaped relative NOSE_BIN resolves under the repository root."""
        (tmp_path / "tools").mkdir()
        stub = write_stub_nose(tmp_path / "tools")
        monkeypatch.setattr(detector, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("NOSE_BIN", "tools/nose")
        assert detector.resolve_binary(stub_settings(), runner=stub_runner()) == str(
            stub
        ), "A relative path must not be re-interpreted as a PATH name."


class TestBuildCommand:
    """Translation of gate settings into a nose query command."""

    def test_pins_every_configured_setting(self, snapshot: SnapshotAssertion) -> None:
        """The whole argument vector is pinned, in order, from the settings.

        Snapshotting the vector keeps the assertion readable as the flag set
        grows, and a change to the order or the spelling of any flag shows up
        as a reviewable diff rather than a wall of inline strings.
        """
        settings = dc.replace(
            stub_settings(),
            roots=("python/stilyagi", "tests/support"),
            mode="semantic",
            min_size=40,
            surface="all",
            top=30,
            exclude=("**/generated/**", "**/_vendor/**"),
        )

        command = detector.build_command("nose", settings)

        assert command == snapshot, (
            "Every configured setting must reach nose, in the documented order."
        )

    def test_default_surface_omits_the_all_term(
        self, snapshot: SnapshotAssertion
    ) -> None:
        """The default surface leaves nose on its ranked dashboard."""
        settings = dc.replace(
            stub_settings(),
            roots=("python/stilyagi",),
            mode="syntax",
            min_size=24,
            surface="default",
            top=None,
            exclude=(),
        )

        command = detector.build_command("nose", settings)

        assert command == snapshot, (
            "The default surface must not widen the view or pass a ranking bound."
        )
