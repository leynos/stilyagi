"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

import pytest

from stilyagi import stilyagi_install

if typ.TYPE_CHECKING:
    from pathlib import Path


class TestEnsureGitignoreEntry:
    """Unit tests for _ensure_gitignore_entry."""

    @pytest.mark.parametrize(
        ("initial_content", "entry", "expected_checks"),
        [
            (
                None,
                "styles/",
                {"file_exists": True, "exact_content": "styles/\n"},
            ),
            (
                "node_modules/\n",
                "styles/",
                {"contains": ["node_modules/", "styles/"]},
            ),
            (
                "styles/\n",
                "styles/",
                {"count": {"styles/": 1}},
            ),
            (
                "styles\n",
                "styles/",
                {"count": {"styles": 1}},
            ),
            (
                "# styles/\n",
                "styles/",
                {"contains": ["# styles/"], "exact_line_count": {"styles/": 1}},
            ),
            (
                "\n\n\n",
                "styles/",
                {"contains": ["styles/"]},
            ),
            (
                "styles/   \n",
                "styles/",
                {"count": {"styles": 1}},
            ),
        ],
        ids=[
            "creates_gitignore_when_missing",
            "appends_entry_when_absent",
            "does_not_duplicate_existing_entry",
            "recognises_entry_without_trailing_slash",
            "ignores_commented_lines",
            "ignores_blank_lines",
            "handles_trailing_whitespace_on_entry",
        ],
    )
    def test_gitignore_entry_handling(
        self,
        tmp_path: Path,
        initial_content: str | None,
        entry: str,
        expected_checks: dict[str, object],
    ) -> None:
        """Verify .gitignore entry handling for various scenarios."""
        gitignore_path = tmp_path / ".gitignore"

        if initial_content is not None:
            gitignore_path.write_text(initial_content, encoding="utf-8")

        stilyagi_install._ensure_gitignore_entry(  # type: ignore[attr-defined]
            gitignore_path=gitignore_path,
            entry=entry,
        )

        if expected_checks.get("file_exists"):
            assert gitignore_path.exists(), "file should exist"

        content = gitignore_path.read_text(encoding="utf-8")

        if "exact_content" in expected_checks:
            assert content == expected_checks["exact_content"], "content mismatch"

        for substring in expected_checks.get("contains", []):
            assert substring in content, f"should contain {substring!r}"

        for substring, expected_count in expected_checks.get("count", {}).items():
            assert content.count(substring) == expected_count, (
                f"{substring!r} count mismatch"
            )

        for pattern, expected_count in expected_checks.get(
            "exact_line_count", {}
        ).items():
            lines = [ln for ln in content.splitlines() if ln.strip() == pattern]
            assert len(lines) == expected_count, (
                f"exact line count for {pattern!r} mismatch"
            )
