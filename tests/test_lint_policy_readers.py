"""Failure modes of the TOML and Makefile lint-policy readers.

The readers in `tests/support/lint_policy.py` are the only route from a test
to `Cargo.toml`, `clippy.toml` and the `Makefile`. A reader that let an
`OSError`, a decoding failure or a structural surprise escape would report as
an incidental traceback, which is indistinguishable from a broken test rather
than a broken policy. These cases pin the contract that every such failure is
a `ReadingError` naming the reader and the path. The one reader that leaves
the filesystem, `member_manifests`, is covered in
`tests/test_lint_policy_metadata.py`.

They write their own files under `tmp_path` and pass the path in, so none of
them reads or perturbs the repository's real configuration.
"""

import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.lint_policy import (
    clippy_restrictions,
    member_inherits_workspace_lints,
    rustdoc_default,
    rustdoc_default_lines,
    workspace_lints,
)
from tests.support.reader_cases import assert_names_reader_and_path, write_text

if typ.TYPE_CHECKING:
    import pathlib


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
    path = write_text(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        workspace_lints(path)
    assert_names_reader_and_path(raised, path)


def test_undecodable_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """Bytes that are not UTF-8 cannot be interpreted as policy."""
    path = tmp_path / "Cargo.toml"
    path.write_bytes(b"[workspace]\nmembers = ['\xff']\n")
    with pytest.raises(ReadingError, match="policy file") as raised:
        workspace_lints(path)
    assert_names_reader_and_path(raised, path)


def test_missing_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A policy file that does not exist names the path it looked for."""
    path = tmp_path / "absent.toml"
    with pytest.raises(ReadingError, match="policy file") as raised:
        workspace_lints(path)
    assert_names_reader_and_path(raised, path)


def test_unreadable_path_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A directory where a file is expected is reported, not raised raw."""
    with pytest.raises(ReadingError, match="policy file") as raised:
        clippy_restrictions(tmp_path)
    assert_names_reader_and_path(raised, tmp_path)


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
    path = write_text(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        workspace_lints(path)
    assert_names_reader_and_path(raised, path)


def test_member_inheritance_reader_accepts_true(tmp_path: pathlib.Path) -> None:
    """A member that opts into the workspace tables reports inheritance."""
    path = write_text(tmp_path / "Cargo.toml", "[lints]\nworkspace = true\n")
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
    path = write_text(tmp_path / "Cargo.toml", document)
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
    assert_names_reader_and_path(raised, path)


def test_member_inheritance_unreadable_path_is_a_reading_error(
    tmp_path: pathlib.Path,
) -> None:
    """A directory where a member manifest is expected is reported, not raised raw."""
    with pytest.raises(ReadingError, match="policy file") as raised:
        member_inherits_workspace_lints(tmp_path)
    assert_names_reader_and_path(raised, tmp_path)


def test_member_inheritance_undecodable_file_is_a_reading_error(
    tmp_path: pathlib.Path,
) -> None:
    """Bytes that are not UTF-8 cannot be interpreted as a member manifest."""
    path = tmp_path / "Cargo.toml"
    path.write_bytes(b"[lints]\nworkspace = '\xff'\n")
    with pytest.raises(ReadingError, match="policy file") as raised:
        member_inherits_workspace_lints(path)
    assert_names_reader_and_path(raised, path)


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
    path = write_text(tmp_path / "Cargo.toml", document)
    with pytest.raises(ReadingError) as raised:
        member_inherits_workspace_lints(path)
    assert_names_reader_and_path(raised, path)


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
    path = write_text(tmp_path / "clippy.toml", document)
    with pytest.raises(ReadingError) as raised:
        clippy_restrictions(path)
    assert_names_reader_and_path(raised, path)


def test_rustdoc_reader_accepts_every_assignment_form(
    tmp_path: pathlib.Path,
) -> None:
    """All assignment operators are matched, and near-misses are not."""
    path = write_text(
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
    path = write_text(tmp_path / "Makefile", "RUSTDOCFLAGS = $(RUSTDOC_FLAGS)\n")
    assert rustdoc_default_lines(path) == [], (
        "expected no assignment to be reported for a reference only"
    )


def test_rustdoc_default_returns_the_single_assignment(
    tmp_path: pathlib.Path,
) -> None:
    """One assignment is returned as the default, stripped."""
    path = write_text(tmp_path / "Makefile", "  RUSTDOC_FLAGS ?= --cfg docsrs\n")
    assert rustdoc_default(path) == "RUSTDOC_FLAGS ?= --cfg docsrs", (
        "expected the one assignment, stripped of surrounding whitespace"
    )


def test_rustdoc_default_rejects_no_assignment(tmp_path: pathlib.Path) -> None:
    """A route with no assignment is a policy finding, not an unpacking error."""
    path = write_text(tmp_path / "Makefile", "RUSTDOCFLAGS = $(RUSTDOC_FLAGS)\n")
    with pytest.raises(ReadingError, match="found 0") as raised:
        rustdoc_default(path)
    assert_names_reader_and_path(raised, path)


def test_rustdoc_default_rejects_two_assignments(tmp_path: pathlib.Path) -> None:
    """A second assignment could replace or extend the default, so it is rejected."""
    path = write_text(
        tmp_path / "Makefile",
        "RUSTDOC_FLAGS ?= --cfg docsrs\nRUSTDOC_FLAGS += --cfg extra\n",
    )
    with pytest.raises(ReadingError, match="found 2") as raised:
        rustdoc_default(path)
    assert_names_reader_and_path(raised, path)
