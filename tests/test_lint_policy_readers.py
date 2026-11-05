"""Failure modes of the lint-policy readers.

The readers in `tests/support/lint_policy.py` are the only route from a test
to `Cargo.toml`, `clippy.toml` and the `Makefile`. A reader that let an
`OSError`, a decoding failure or a structural surprise escape would report as
an incidental traceback, which is indistinguishable from a broken test rather
than a broken policy. These cases pin the contract that every such failure is
a `ReadingError` naming the reader and the path.

They write their own files under `tmp_path` and pass the path in, so none of
them reads or perturbs the repository's real configuration.
"""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - builds fake `cargo metadata` outcomes, runs nothing.
import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.lint_policy import (
    MetadataRunner,
    clippy_restrictions,
    member_inherits_workspace_lints,
    member_manifests,
    rustdoc_default,
    rustdoc_default_lines,
    workspace_lints,
)

if typ.TYPE_CHECKING:
    import pathlib


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    """Write `text` and return the path, for use as a reader argument."""
    path.write_text(text, encoding="utf-8")
    return path


def _assert_names_reader_and_path(
    raised: pytest.ExceptionInfo[ReadingError], path: pathlib.Path
) -> None:
    """Assert the failure names the lint-policy reader and the requested path."""
    assert raised.value.reader == "lint_policy", (
        f"expected the lint_policy reader, got {raised.value.reader!r}"
    )
    assert raised.value.path == str(path), (
        f"expected the requested path {str(path)!r}, got {raised.value.path!r}"
    )


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("", id="empty"),
        pytest.param("[workspace\n", id="truncated"),
        pytest.param("[workspace]\nmembers = [\n", id="unterminated-array"),
    ],
)
def test_malformed_toml_is_a_reading_error(
    tmp_path: pathlib.Path, document: str
) -> None:
    """Invalid TOML surfaces as a policy finding, not a parser traceback."""
    path = _write(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


def test_undecodable_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """Bytes that are not UTF-8 cannot be interpreted as policy."""
    path = tmp_path / "Cargo.toml"
    path.write_bytes(b"[workspace]\nmembers = ['\xff']\n")
    with pytest.raises(ReadingError, match="policy file") as raised:
        workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


def test_missing_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A policy file that does not exist names the path it looked for."""
    path = tmp_path / "absent.toml"
    with pytest.raises(ReadingError, match="policy file") as raised:
        workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


def test_unreadable_path_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A directory where a file is expected is reported, not raised raw."""
    with pytest.raises(ReadingError, match="policy file") as raised:
        clippy_restrictions(tmp_path)
    _assert_names_reader_and_path(raised, tmp_path)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("[package]\nname = 'probe'\n", id="no-workspace-table"),
        pytest.param("[workspace]\nlints = 3\n", id="lints-not-a-table"),
        pytest.param("[workspace.lints]\nclippy = 'deny'\n", id="namespace-not-table"),
    ],
)
def test_structural_surprises_are_reading_errors(
    tmp_path: pathlib.Path, document: str
) -> None:
    """A manifest with an unexpected shape is rejected, not partially read."""
    path = _write(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("[workspace]\n", id="no-member-list"),
        pytest.param("[workspace]\nmembers = [1]\n", id="member-not-a-string"),
    ],
)
def test_member_list_failures_are_reading_errors(
    tmp_path: pathlib.Path, document: str
) -> None:
    """An unusable member list is a finding rather than a skipped pattern."""
    path = _write(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        member_manifests(path)
    _assert_names_reader_and_path(raised, path)


def _completed(
    stdout: str, *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Return a `cargo metadata` outcome for a fake runner to report."""
    return subprocess.CompletedProcess(
        args=["cargo", "metadata"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _returns(result: subprocess.CompletedProcess[str]) -> MetadataRunner:
    """Return a metadata runner that always reports `result`."""
    return lambda _path: result


def test_member_discovery_reads_the_runner_document(tmp_path: pathlib.Path) -> None:
    """Members come from the metadata document, not from the patterns."""
    manifest = _write(tmp_path / "Cargo.toml", "[workspace]\nmembers = []\n")
    member = tmp_path / "crates" / "probe" / "Cargo.toml"
    outsider = tmp_path / "vendor" / "other" / "Cargo.toml"
    document = json.dumps({
        "workspace_members": ["probe 0.1.0 (path+file:///tree/probe)"],
        "packages": [
            {
                "id": "probe 0.1.0 (path+file:///tree/probe)",
                "manifest_path": str(member),
            },
            {
                "id": "other 0.1.0 (path+file:///tree/other)",
                "manifest_path": str(outsider),
            },
        ],
    })
    manifests = member_manifests(manifest, run_metadata=_returns(_completed(document)))
    assert manifests == (member,), (
        f"expected only the workspace member, got {manifests}"
    )


def test_member_discovery_reports_a_failed_runner(tmp_path: pathlib.Path) -> None:
    """A runner that exits non-zero is a finding naming the reader and path."""
    manifest = _write(tmp_path / "Cargo.toml", "[workspace]\nmembers = []\n")
    failed = _completed("", returncode=101, stderr="error: no network")
    with pytest.raises(ReadingError) as raised:
        member_manifests(manifest, run_metadata=_returns(failed))
    _assert_names_reader_and_path(raised, manifest)
    assert "no network" in str(raised.value), (
        f"expected the runner's stderr in {raised.value}"
    )


def test_member_discovery_reports_an_invalid_document(tmp_path: pathlib.Path) -> None:
    """A runner that returns non-JSON is a finding, not a traceback."""
    manifest = _write(tmp_path / "Cargo.toml", "[workspace]\nmembers = []\n")
    with pytest.raises(ReadingError) as raised:
        member_manifests(manifest, run_metadata=_returns(_completed("not json")))
    _assert_names_reader_and_path(raised, manifest)


def test_member_inheritance_reader_accepts_true(tmp_path: pathlib.Path) -> None:
    """A member that opts into the workspace tables reports inheritance."""
    path = _write(tmp_path / "Cargo.toml", "[lints]\nworkspace = true\n")
    assert member_inherits_workspace_lints(path) is True, (
        "expected `workspace = true` to report inheritance"
    )


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("[package]\nname = 'probe'\n", id="no-lints-table"),
        pytest.param("[lints]\nworkspace = false\n", id="workspace-false"),
        pytest.param("[lints]\nworkspace = 'true'\n", id="workspace-not-a-bool"),
        pytest.param("[lints]\n", id="workspace-absent"),
    ],
)
def test_member_inheritance_reader_rejects_everything_else(
    tmp_path: pathlib.Path, document: str
) -> None:
    """Only a literal `workspace = true` counts as opting in."""
    path = _write(tmp_path / "Cargo.toml", document)
    assert member_inherits_workspace_lints(path) is False, (
        "expected anything other than `workspace = true` to report no inheritance"
    )


def test_member_inheritance_missing_file_is_a_reading_error(
    tmp_path: pathlib.Path,
) -> None:
    """A member manifest that does not exist names the path it looked for."""
    path = tmp_path / "absent" / "Cargo.toml"
    with pytest.raises(ReadingError, match="policy file") as raised:
        member_inherits_workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


def test_member_inheritance_unreadable_path_is_a_reading_error(
    tmp_path: pathlib.Path,
) -> None:
    """A directory where a member manifest is expected is reported, not raised raw."""
    with pytest.raises(ReadingError, match="policy file") as raised:
        member_inherits_workspace_lints(tmp_path)
    _assert_names_reader_and_path(raised, tmp_path)


def test_member_inheritance_undecodable_file_is_a_reading_error(
    tmp_path: pathlib.Path,
) -> None:
    """Bytes that are not UTF-8 cannot be interpreted as a member manifest."""
    path = tmp_path / "Cargo.toml"
    path.write_bytes(b"[lints]\nworkspace = '\xff'\n")
    with pytest.raises(ReadingError, match="policy file") as raised:
        member_inherits_workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("[lints\n", id="truncated"),
        pytest.param("[lints]\nworkspace = [\n", id="unterminated-array"),
    ],
)
def test_member_inheritance_malformed_file_is_a_reading_error(
    tmp_path: pathlib.Path, document: str
) -> None:
    """Invalid TOML in a member manifest surfaces as a policy finding."""
    path = _write(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        member_inherits_workspace_lints(path)
    _assert_names_reader_and_path(raised, path)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("", id="no-restrictions"),
        pytest.param("disallowed-methods = 'std::env::var'\n", id="not-a-list"),
        pytest.param("disallowed-methods = [1]\n", id="entry-not-a-table"),
        pytest.param(
            'disallowed-methods = [{ path = "std::env::var" }, "std::env::vars"]\n',
            id="mixed-entries",
        ),
    ],
)
def test_clippy_restriction_failures_are_reading_errors(
    tmp_path: pathlib.Path, document: str
) -> None:
    """A malformed restriction list is reported, never silently filtered."""
    path = _write(tmp_path / "clippy.toml", document)
    with pytest.raises(ReadingError) as raised:
        clippy_restrictions(path)
    _assert_names_reader_and_path(raised, path)


def test_rustdoc_reader_accepts_every_assignment_form(
    tmp_path: pathlib.Path,
) -> None:
    """All assignment operators are matched, and near-misses are not."""
    path = _write(
        tmp_path / "Makefile",
        "\n".join([
            "# RUSTDOC_FLAGS ?= commented out",
            "RUSTDOC_FLAGS_EXTRA ?=",
            "RUSTDOCFLAGS = not this variable",
            "RUSTDOC_FLAGS ?= --cfg docsrs",
            "  export RUSTDOC_FLAGS += --cfg extra",
            "override RUSTDOC_FLAGS := --cfg docsrs",
        ]),
    )
    assert rustdoc_default_lines(path) == [
        "RUSTDOC_FLAGS ?= --cfg docsrs",
        "export RUSTDOC_FLAGS += --cfg extra",
        "override RUSTDOC_FLAGS := --cfg docsrs",
    ], "expected every RUSTDOC_FLAGS assignment and no near-miss"


def test_rustdoc_reader_reports_no_assignment(tmp_path: pathlib.Path) -> None:
    """A Makefile that never assigns the variable yields an empty list."""
    path = _write(tmp_path / "Makefile", "RUSTDOCFLAGS = $(RUSTDOC_FLAGS)\n")
    assert rustdoc_default_lines(path) == [], (
        "expected no assignment to be reported for a reference only"
    )


def test_rustdoc_default_returns_the_single_assignment(
    tmp_path: pathlib.Path,
) -> None:
    """One assignment is returned as the default, stripped."""
    path = _write(tmp_path / "Makefile", "  RUSTDOC_FLAGS ?= --cfg docsrs\n")
    assert rustdoc_default(path) == "RUSTDOC_FLAGS ?= --cfg docsrs", (
        "expected the one assignment, stripped of surrounding whitespace"
    )


def test_rustdoc_default_rejects_no_assignment(tmp_path: pathlib.Path) -> None:
    """A route with no assignment is a policy finding, not an unpacking error."""
    path = _write(tmp_path / "Makefile", "RUSTDOCFLAGS = $(RUSTDOC_FLAGS)\n")
    with pytest.raises(ReadingError, match="found 0") as raised:
        rustdoc_default(path)
    _assert_names_reader_and_path(raised, path)


def test_rustdoc_default_rejects_two_assignments(tmp_path: pathlib.Path) -> None:
    """A second assignment could replace or extend the default, so it is rejected."""
    path = _write(
        tmp_path / "Makefile",
        "RUSTDOC_FLAGS ?= --cfg docsrs\nRUSTDOC_FLAGS += --cfg extra\n",
    )
    with pytest.raises(ReadingError, match="found 2") as raised:
        rustdoc_default(path)
    _assert_names_reader_and_path(raised, path)
