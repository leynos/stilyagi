"""Resolve the workspace member set through a constrained `cargo metadata`.

Cargo's member set is wider than the `members` patterns in the root manifest: a
path dependency that lives inside the workspace directory becomes a member even
when no pattern matches it. Reading only the patterns would let such a member
omit `[lints] workspace = true` without failing the lint-policy contract, so the
set comes from Cargo itself.

The invocation is deliberately narrow. `--no-deps` stops Cargo resolving the
dependency graph, `--locked` refuses to update `Cargo.lock`, and `--offline`
refuses to fetch, so discovery reads manifests and compiles nothing. The
invocation is taken through `MetadataRunner`, a callable seam, so reader tests
inject a fake outcome and one contract test crosses the real boundary.

This module is separate from `tests.support.lint_policy` because it is the one
reader that leaves the filesystem; the TOML and Makefile readers stay there.
"""

import collections.abc as cabc
import json
import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned `cargo metadata`, which compiles nothing.
import typing as typ

from tests.support.errors import ReadingError
from tests.support.lint_policy import WORKSPACE_MANIFEST, workspace_table

#: `cargo metadata --no-deps` reads manifests and resolves the workspace, so
#: it is quick; the timeout only stops a wedged Cargo from hanging the suite.
CARGO_METADATA_TIMEOUT_SECONDS: typ.Final = 120.0

#: The seam `member_manifests` accepts; the default is the real runner.
type MetadataRunner = cabc.Callable[[pathlib.Path], subprocess.CompletedProcess[str]]


def _run_cargo_metadata(path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Run the constrained `cargo metadata` and return its outcome."""
    cargo = shutil.which("cargo")
    if cargo is None:
        message = "cargo is required to resolve workspace members"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    try:
        return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv: `cargo metadata` reads manifests only.
            [
                cargo,
                "metadata",
                "--no-deps",
                "--locked",
                "--offline",
                "--format-version",
                "1",
                "--manifest-path",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=CARGO_METADATA_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        message = (
            "cargo metadata did not finish within "
            f"{CARGO_METADATA_TIMEOUT_SECONDS:g} seconds"
        )
        raise ReadingError(message, reader="lint_policy", path=str(path)) from error
    except OSError as error:
        message = f"cargo metadata could not start: {error}"
        raise ReadingError(message, reader="lint_policy", path=str(path)) from error


def member_manifests(
    path: pathlib.Path = WORKSPACE_MANIFEST,
    *,
    run_metadata: MetadataRunner = _run_cargo_metadata,
) -> tuple[pathlib.Path, ...]:
    """Return every workspace member manifest, as Cargo resolves them.

    Cargo's member set is wider than the `members` patterns: a path dependency
    that lives inside the workspace directory becomes a member too, even when
    no pattern matches it. Reading only the patterns would let such a member
    omit `[lints] workspace = true` without failing the contract, so the set
    comes from `cargo metadata --no-deps` after the manifest's own shape is
    validated.

    Parameters
    ----------
    path
        The workspace manifest to resolve; the default is this repository's.
    run_metadata
        The metadata runner; the default is the real, constrained
        `cargo metadata` invocation.

    Returns
    -------
    tuple
        Each member's `Cargo.toml`, in sorted order.

    Raises
    ------
    ReadingError
        If the manifest cannot be read or parsed, declares no member list, a
        member pattern is not a string, Cargo is unavailable, or Cargo cannot
        resolve the workspace.
    """
    _require_member_list(path)
    metadata = _cargo_metadata(path, run_metadata)
    member_ids = metadata.get("workspace_members")
    packages = metadata.get("packages")
    if not isinstance(member_ids, list) or not isinstance(packages, list):
        message = "cargo metadata reported no workspace members"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    wanted = {member for member in member_ids if isinstance(member, str)}
    manifests = [
        pathlib.Path(package["manifest_path"])
        for package in packages
        if isinstance(package, dict)
        and package.get("id") in wanted
        and isinstance(package.get("manifest_path"), str)
    ]
    return tuple(sorted(manifests))


def _require_member_list(path: pathlib.Path) -> None:
    """Raise unless the manifest declares a list of string member patterns."""
    patterns = workspace_table(path).get("members")
    if not isinstance(patterns, list):
        message = "Cargo.toml declares no member list"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    for pattern in patterns:
        if not isinstance(pattern, str):
            message = f"member pattern {pattern!r} is not a string"
            raise ReadingError(message, reader="lint_policy", path=str(path))


def _cargo_metadata(
    path: pathlib.Path, run_metadata: MetadataRunner
) -> dict[str, object]:
    """Return the metadata document the runner produced for `path`."""
    result = run_metadata(path)
    if result.returncode != 0:
        message = f"cargo metadata failed: {result.stderr.strip()}"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    return _metadata_document(result.stdout, path)


def _metadata_document(stdout: str, path: pathlib.Path) -> dict[str, object]:
    """Parse `cargo metadata` output, rejecting a non-object document."""
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError as error:
        message = f"cargo metadata returned invalid JSON: {error}"
        raise ReadingError(message, reader="lint_policy", path=str(path)) from error
    if not isinstance(document, dict):
        message = "cargo metadata returned a non-object document"
        raise ReadingError(message, reader="lint_policy", path=str(path))
    return document
