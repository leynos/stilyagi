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

import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.lint_policy import (
    clippy_restrictions,
    member_manifests,
    rustdoc_default_lines,
    workspace_lints,
)

if typ.TYPE_CHECKING:
    import pathlib


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    """Write `text` and return the path, for use as a reader argument."""
    path.write_text(text, encoding="utf-8")
    return path


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
    with pytest.raises(ReadingError):
        workspace_lints(_write(tmp_path / "Cargo.toml", document))


def test_undecodable_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """Bytes that are not UTF-8 cannot be interpreted as policy."""
    path = tmp_path / "Cargo.toml"
    path.write_bytes(b"[workspace]\nmembers = ['\xff']\n")
    with pytest.raises(ReadingError):
        workspace_lints(path)


def test_missing_file_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A policy file that does not exist names the path it looked for."""
    with pytest.raises(ReadingError, match="policy file"):
        workspace_lints(tmp_path / "absent.toml")


def test_unreadable_path_is_a_reading_error(tmp_path: pathlib.Path) -> None:
    """A directory where a file is expected is reported, not raised raw."""
    with pytest.raises(ReadingError, match="policy file"):
        clippy_restrictions(tmp_path)


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
    with pytest.raises(ReadingError):
        workspace_lints(_write(tmp_path / "Cargo.toml", document))


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
    with pytest.raises(ReadingError):
        member_manifests(_write(tmp_path / "Cargo.toml", document))


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
    with pytest.raises(ReadingError):
        clippy_restrictions(_write(tmp_path / "clippy.toml", document))


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
