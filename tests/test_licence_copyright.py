"""Contract test tying the licence copyright year to the repository's history.

The copyright notice in ``LICENSE`` names a year range. Its closing year has
to keep pace with the work: a repository that gained code or documentation in
a later year than its own copyright notice claims is making a stale
assertion about itself.

Run with ``python -m pytest tests/test_licence_copyright.py -v``. When this
fails, the fix is to widen the year in ``LICENSE``, not to relax the test.
"""

import pathlib
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the test invokes git with a fixed argument list.

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
LICENCE_PATH = REPOSITORY_ROOT / "LICENSE"

_GIT_TIMEOUT_SECONDS = 30

#: Matches the year, or the closing year of a range, in the copyright line.
#: Both "2025" and "2025-2026" are accepted, with either a hyphen or an en
#: dash separating a range.
# The en dash is written as an escape so the pattern holds no ambiguous
# character; `re` expands it.
_COPYRIGHT_RE = re.compile(r"Copyright\s+©\s+(\d{4})(?:\s*[-\u2013]\s*(\d{4}))?")

#: The suffixes that count as code or documentation for this contract.
#: Lockfiles, snapshots, and binary fixtures are deliberately absent: they
#: change as a consequence of the work rather than constituting it.
_TRACKED_SUFFIXES = frozenset({
    ".py",
    ".rs",
    ".md",
    ".toml",
    ".jinja",
    ".yaml",
    ".yml",
    ".sh",
})


def _run_git(*args: str) -> str:
    """Return stdout from ``git`` in the repository root.

    Returns
    -------
    str
        The command's standard output.
    """
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument list, no shell.
        ["git", *args],  # ruff: ignore[start-process-with-partial-path] - git is resolved from PATH by design.
        capture_output=True,
        check=True,
        cwd=REPOSITORY_ROOT,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    return completed.stdout


def _licence_years() -> tuple[int, int]:
    """Return the opening and closing years of the copyright notice.

    A single year is treated as a range that opens and closes in the same
    year.

    Returns
    -------
    tuple[int, int]
        The opening and closing years, respectively.
    """
    text = LICENCE_PATH.read_text(encoding="utf-8")
    match = _COPYRIGHT_RE.search(text)
    assert match is not None, (
        f"{LICENCE_PATH.name} should carry a 'Copyright © <year>' notice"
    )
    opened = int(match.group(1))
    closed = int(match.group(2) or match.group(1))
    return opened, closed


def _is_own_git_worktree() -> bool:
    """Report whether this tree is the root of its own git repository.

    Guards two ways of getting a wrong answer rather than no answer. An
    unpacked tarball has no repository at all, so git fails outright. A copy
    dropped inside some other checkout has one, but it is not this project's
    — git would happily date that repository's files instead. Comparing the
    reported top level against this tree rules both out.

    Returns
    -------
    bool
        Whether the repository root reported by Git is this tree.
    """
    try:
        top_level = _run_git("rev-parse", "--show-toplevel").strip()
    except subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError:
        return False

    if not top_level:
        return False

    return pathlib.Path(top_level).resolve() == REPOSITORY_ROOT


def _latest_authored_year() -> int | None:
    """Return the year of the most recent commit touching code or docs.

    Uses the author date, which survives the rebases this repository's
    branches go through, rather than the committer date, which does not.

    Returns
    -------
    int | None
        ``None`` when the history cannot answer the question: git missing,
        the tree unpacked outside a repository, a shallow continuous-
        integration clone, or a copy nested inside some other repository.
    """
    if not _is_own_git_worktree():
        return None

    try:
        tracked = _run_git("ls-files", "-z").split("\0")
    except subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError:
        return None

    paths = [
        name
        for name in tracked
        if name and pathlib.PurePosixPath(name).suffix in _TRACKED_SUFFIXES
    ]
    if not paths:
        return None

    try:
        stdout = _run_git("log", "-1", "--format=%ad", "--date=format:%Y", "--", *paths)
    except subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError:
        return None

    year = stdout.strip()
    return int(year) if year.isdigit() else None


class TestLicenceCopyright:
    """The copyright notice keeps pace with the repository's own history."""

    def test_licence_file_is_present(self) -> None:
        """The metadata promises a licence file, so one must exist."""
        assert LICENCE_PATH.is_file(), f"{LICENCE_PATH} should exist"

    def test_copyright_range_is_ordered(self) -> None:
        """A range that closes before it opens is a typo, not a range."""
        opened, closed = _licence_years()

        assert opened <= closed, (
            f"copyright range {opened}-{closed} closes before it opens"
        )

    def test_copyright_covers_the_latest_change(self) -> None:
        """The notice must not claim a year earlier than the newest work."""
        latest = _latest_authored_year()
        if latest is None:
            pytest.skip(
                "untestable here: dating the tree needs this repository's own "
                "git history, which is absent outside a checkout, in a shallow "
                "clone, or in a copy nested inside another repository"
            )

        _opened, closed = _licence_years()

        assert closed >= latest, (
            f"{LICENCE_PATH.name} claims copyright through {closed}, but code or "
            f"documentation was last authored in {latest}. Widen the year range "
            f"in {LICENCE_PATH.name}."
        )
