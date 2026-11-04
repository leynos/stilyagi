"""Hold the tag's version check to the comparison it makes.

``check-version`` is the gate that stops a tag whose ``pyproject.toml`` version
disagrees with the tag, and its other output is the ``prerelease`` flag the
GitHub Release is created with. Both come from ``scripts/release_version.py``,
which the workflow only ever runs as a subprocess, so no test that executes the
step instruments it and a regression there would ship unmeasured.

This module calls the script's functions in process for every spelling the
comparison answers, and runs the workflow's own command through
``tests.support.release_steps.run_version_check`` for the two verdicts the job
acts on: a matching tag that publishes, and a disagreeing one that must not.
"""

import typing as typ

import pytest

from scripts import release_version
from tests.support.release_fakes import fake_release
from tests.support.release_steps import requires_bash, run_version_check
from tests.support.release_workflow import REPOSITORY_ROOT, link_scripts

if typ.TYPE_CHECKING:
    import pathlib

ANNOTATION: typ.Final = (
    "::error file=pyproject.toml,title=Tag/pyproject.toml mismatch::"
)


def _declare(root: pathlib.Path, version: str) -> None:
    """Write a ``pyproject.toml`` declaring `version` into `root`."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "stilyagi"\nversion = "{version}"\n', encoding="utf-8"
    )


def _output(root: pathlib.Path) -> pathlib.Path:
    """Return the ``GITHUB_OUTPUT`` path, which no step creates until it writes."""
    return root / "github-output"


def _environ(root: pathlib.Path, tag_version: str) -> dict[str, str]:
    """Return the environment the step receives: the tag and its output file."""
    return {"TAG_VERSION": tag_version, "GITHUB_OUTPUT": str(_output(root))}


# -- is_prerelease -----------------------------------------------------------


@pytest.mark.parametrize(
    "version",
    ["0.2.0", "1.2.3", "12.0.0", "1.2.3.post1", "1.2.3+rc.1"],
    ids=["release", "patch", "major", "post", "local-label"],
)
def test_an_ordinary_release_is_not_a_prerelease(version: str) -> None:
    """A post-release marker and a local label never make a pre-release."""
    assert release_version.is_prerelease(version) is False, version


@pytest.mark.parametrize(
    "version",
    [
        "0.2.0-beta1",
        "1.2.3rc1",
        "1.2.3a1",
        "1.2.3b2",
        "1.2.3c1",
        "1.2.3.dev3",
        "1.2.3-pre",
        "0.2.0-preview.1",
        "1.2.3RC1",
        "1.2.3.1adev3",
    ],
)
def test_a_marked_version_is_a_prerelease(version: str) -> None:
    """Every PEP 440 pre-release label is found, in either case."""
    assert release_version.is_prerelease(version) is True, version


def test_a_local_label_is_not_read_as_a_marker() -> None:
    """``+`` starts build metadata, which the public version excludes."""
    assert release_version.is_prerelease("1.2.3+rc.1") is False, "a label is metadata"
    assert release_version.is_prerelease("1.2.3rc1+local") is True, "the marker counts"


# -- main --------------------------------------------------------------------


def test_a_matching_tag_reports_a_final_release(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A matching tag writes the flag the release job reads, and exits zero."""
    _declare(tmp_path, "0.2.0")
    completed = release_version.main(_environ(tmp_path, "0.2.0"), tmp_path)
    assert completed == 0, "a matching tag failed the check"
    written = _output(tmp_path).read_text(encoding="utf-8")
    assert written == "prerelease=false\n", written
    printed = capsys.readouterr().out
    assert "Release tag 0.2.0 matches pyproject.toml." in printed, printed


def test_a_marked_tag_reports_a_prerelease(tmp_path: pathlib.Path) -> None:
    """The same comparison hands the release one flag for a marked tag."""
    _declare(tmp_path, "0.2.0-beta1")
    completed = release_version.main(_environ(tmp_path, "0.2.0-beta1"), tmp_path)
    assert completed == 0, "a marked tag failed the check"
    written = _output(tmp_path).read_text(encoding="utf-8")
    assert written == "prerelease=true\n", written


def test_a_disagreeing_tag_fails_without_writing_a_flag(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mismatch annotates both versions and reports nothing downstream."""
    _declare(tmp_path, "0.2.0")
    assert release_version.main(_environ(tmp_path, "0.2.0-beta1"), tmp_path) == 1, (
        "a disagreeing tag passed the check"
    )
    assert not _output(tmp_path).exists(), "a failed check reported a flag"
    printed = capsys.readouterr().out
    assert ANNOTATION in printed, printed
    assert (
        "Tag version 0.2.0-beta1 does not match pyproject.toml version 0.2.0" in printed
    ), printed


# -- the workflow's own command ----------------------------------------------


def _checked_out(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a working directory holding the repository's linked ``scripts/``."""
    work = tmp_path / "work"
    work.mkdir()
    link_scripts(REPOSITORY_ROOT, work)
    return work


@requires_bash
def test_the_step_runs_the_checked_in_script(tmp_path: pathlib.Path) -> None:
    """The job's command reaches the same verdict as the function does."""
    work = _checked_out(tmp_path)
    completed, written = run_version_check(
        work,
        declared="0.2.0",
        tag_version="0.2.0",
        environ=fake_release(tmp_path).environ(),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert written == {"prerelease": "false"}, written


@requires_bash
def test_the_step_fails_a_tag_the_manifest_disagrees_with(
    tmp_path: pathlib.Path,
) -> None:
    """The script, not only the function, stops a release for a wrong tag."""
    work = _checked_out(tmp_path)
    completed, written = run_version_check(
        work,
        declared="0.2.0",
        tag_version="0.1.9",
        environ=fake_release(tmp_path).environ(),
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert not written, "a failed check reported a flag"
    assert ANNOTATION in completed.stdout, completed.stdout
