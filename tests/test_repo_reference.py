"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import pytest

from stilyagi import stilyagi


@pytest.mark.parametrize(
    ("repo_ref", "expected_owner", "expected_repo", "expected_style"),
    [
        ("owner/repo", "owner", "repo", "repo"),
        ("owner/repo-vale", "owner", "repo-vale", "repo"),
    ],
)
def test_parse_repo_reference_valid_inputs(
    repo_ref: str, expected_owner: str, expected_repo: str, expected_style: str
) -> None:
    """_parse_repo_reference returns (owner, repo_name, style_name) for valid inputs."""
    result = stilyagi._parse_repo_reference(repo_ref)  # type: ignore[attr-defined]
    assert result == (expected_owner, expected_repo, expected_style), (
        f"Repository reference {repo_ref!r} should parse correctly"
    )


@pytest.mark.parametrize(
    "repo_ref",
    [
        "owner",  # no slash
        "owner/repo/xyz",  # too many segments
        "/repo",  # missing owner
        "owner/",  # missing repo name
        "/",  # both segments empty
        "   /repo",  # whitespace owner
        "owner/   ",  # whitespace repo
        "   /   ",  # whitespace owner and repo
    ],
)
def test_parse_repo_reference_invalid_inputs(repo_ref: str) -> None:
    """_parse_repo_reference rejects malformed repo references with a clear error."""
    with pytest.raises(
        ValueError,
        match=r"Repository reference must be in the form ['\"]owner/name['\"]",
    ):
        stilyagi._parse_repo_reference(repo_ref)  # type: ignore[attr-defined]
