"""Hold the release stand-ins to the behaviour the publishing tests rest on.

``tests/support/release_clients.py`` serves ``curl`` and ``gh`` for every test
that executes a publishing step, and those tests read its answers as evidence:
a re-run uploads nothing because the fake refuses a name it already holds, and
a gap on the release is filled from PyPI because the fake's index and its
download agree. A stand-in that quietly overwrote an asset, or served a file
PyPI does not list, would leave those tests passing while the real command
failed on a tag.

The publishing tests reach the stand-ins only as subprocesses, so their bodies
run inside a shell and are never asserted against directly. This module drives
each one in process and checks the deviations its own docstring claims:
refusal rather than clobber, a non-zero exit for a file the index does not
name, and a journal recording what ran.
"""

import hashlib
import itertools
import json
import typing as typ

import pytest

from tests.support.release_clients import FILES_URL, RELEASE_TAG, curl, gh
from tests.support.release_fake import main
from tests.support.release_fakes import FakeRelease, fake_release

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

INDEX_URL: typ.Final = "https://pypi.org/simple/stilyagi/"
WHEEL: typ.Final = "stilyagi-0.2.0-cp314-cp314-manylinux_2_28_x86_64.whl"
SDIST: typ.Final = "stilyagi-0.2.0.tar.gz"


@pytest.fixture
def release(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> FakeRelease:
    """Return fakes rooted at `tmp_path`, with every state variable pointing there."""
    fake = fake_release(tmp_path)
    for variable, value in (
        ("FAKE_RELEASE_JOURNAL", fake.journal),
        ("FAKE_RELEASE_GITHUB", fake.github),
        ("FAKE_RELEASE_PYPI", fake.pypi),
        ("FAKE_RELEASE_STATE", fake.root / "release-state.json"),
    ):
        monkeypatch.setenv(variable, str(value))
    return fake


def _digest(payload: bytes) -> str:
    """Return the hex SHA-256 the stand-ins report for `payload`."""
    return hashlib.sha256(payload).hexdigest()


#: The two files both destinations hold, and the bytes each one carries.
_HELD: typ.Final = ((WHEEL, b"wheel"), (SDIST, b"sdist"))


def _listed(name: str, payload: bytes) -> dict[str, str]:
    """Return one asset as ``gh release view`` reports it."""
    return {"name": name, "digest": f"sha256:{_digest(payload)}"}


def _indexed(name: str, payload: bytes) -> dict[str, object]:
    """Return one file as the PEP 691 simple index names it."""
    return {
        "filename": name,
        "url": f"{FILES_URL}{name}",
        "hashes": {"sha256": _digest(payload)},
    }


def _state(fake: FakeRelease) -> dict[str, object]:
    """Return the draft/prerelease state the fake recorded."""
    path = fake.root / "release-state.json"
    return typ.cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


# -- gh release view ---------------------------------------------------------


def test_the_view_reports_each_asset_with_its_digest(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """The listing is what ``gh release view --json assets`` prints."""
    (release.github / WHEEL).write_bytes(b"wheel")
    (release.github / SDIST).write_bytes(b"sdist")
    completed = gh(["release", "view", RELEASE_TAG, "--json", "assets"])
    assert completed == 0, "the view must succeed"
    view = json.loads(capsys.readouterr().out)
    # Sorted by name, as ``gh`` reports them: the hyphen in ``-cp314`` sorts
    # before the dot in ``.tar.gz``, so the wheel leads.
    expected = list(itertools.starmap(_listed, _HELD))
    assert view == {"assets": expected}, view


def test_a_fresh_release_has_recorded_no_calls(release: FakeRelease) -> None:
    """The journal appears with the first invocation, so its absence means none."""
    assert release.calls("gh") == [], "a fresh fake recorded an invocation"


def test_the_view_honours_a_scripted_failure(
    release: FakeRelease,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A scripted status exits without printing a listing to be parsed."""
    monkeypatch.setenv("FAKE_RELEASE_VIEW_STATUS", "1")
    completed = gh(["release", "view", RELEASE_TAG, "--json", "assets"])
    assert completed == 1, "the scripted status must be the exit status"
    assert not capsys.readouterr().out, "a failing view must print no listing"


# -- gh release upload -------------------------------------------------------


def test_an_upload_refuses_to_clobber(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """``gh`` rejects ``--clobber`` here so no test can come to rely on it."""
    source = release.root / WHEEL
    source.write_bytes(b"wheel")
    completed = gh(["release", "upload", RELEASE_TAG, "--clobber", str(source)])
    assert completed == 1, "the fake must refuse --clobber"
    assert not (release.github / WHEEL).exists(), "nothing may have been written"
    complaint = capsys.readouterr().err
    assert "--clobber" in complaint, complaint


def test_an_upload_refuses_a_name_the_release_already_holds(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second upload of one name fails and leaves the held bytes alone."""
    (release.github / WHEEL).write_bytes(b"held")
    source = release.root / WHEEL
    source.write_bytes(b"replacement")
    completed = gh(["release", "upload", RELEASE_TAG, str(source)])
    assert completed == 1, "a held name must not be replaced"
    assert (release.github / WHEEL).read_bytes() == b"held", "the asset was replaced"
    complaint = capsys.readouterr().err
    assert WHEEL in complaint, complaint


@pytest.mark.parametrize(
    "options",
    [
        ("--repo", "leynos/stilyagi", "--notes-file", "notes.md"),
        ("--repo=leynos/stilyagi", "--notes-file=notes.md"),
    ],
    ids=["separate", "joined"],
)
def test_an_upload_copies_only_file_operands(
    release: FakeRelease, options: tuple[str, ...]
) -> None:
    """An option's value is not a file, in either spelling of the option."""
    source = release.root / WHEEL
    source.write_bytes(b"wheel")
    completed = gh(["release", "upload", RELEASE_TAG, str(source), *options])
    assert completed == 0, "the values were read as files"
    assert (release.github / WHEEL).read_bytes() == b"wheel", "the wheel changed"


# -- gh release download -----------------------------------------------------


def _download(destination: pathlib.Path) -> int:
    """Download `WHEEL` from the fake release into `destination`."""
    return gh([
        "release",
        "download",
        RELEASE_TAG,
        "--pattern",
        WHEEL,
        "--dir",
        str(destination),
    ])


def test_a_download_refuses_an_asset_the_release_lacks(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing asset is an error, not an empty file."""
    destination = release.root / "fetched"
    assert _download(destination) == 1, "a missing asset must fail"
    assert not destination.exists(), "no directory is made for a missing asset"
    complaint = capsys.readouterr().err
    assert WHEEL in complaint, complaint


def test_a_download_copies_the_asset_into_its_directory(
    release: FakeRelease,
) -> None:
    """The bytes land under the requested directory, named as they were."""
    (release.github / WHEEL).write_bytes(b"held")
    destination = release.root / "fetched"
    assert _download(destination) == 0, "a held asset must download"
    assert (destination / WHEEL).read_bytes() == b"held", "the bytes differ"


# -- gh release create and edit ----------------------------------------------


def test_a_create_records_the_flags_it_was_given(
    release: FakeRelease,
) -> None:
    """A created release is a draft, and its prerelease state is recorded."""
    completed = gh(["release", "create", RELEASE_TAG, "--draft", "--prerelease"])
    assert completed == 0, "the create must succeed"
    assert _state(release) == {"draft": True, "prerelease": True}, _state(release)


def test_a_create_honours_a_scripted_failure(
    release: FakeRelease, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reuse path is driven by this status, so it must be able to fail."""
    monkeypatch.setenv("FAKE_RELEASE_CREATE_STATUS", "1")
    completed = gh([
        "release",
        "create",
        RELEASE_TAG,
        "--draft",
    ])
    assert completed == 1, "the create was scripted to fail"
    assert not (release.root / "release-state.json").exists(), "state was written"


def test_an_edit_refuses_a_release_that_was_never_created(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """Editing an absent release fails rather than inventing one."""
    completed = gh(["release", "edit", RELEASE_TAG, "--draft=false"])
    assert completed == 1, "editing an absent release must fail"
    complaint = capsys.readouterr().err
    assert "not found" in complaint, complaint


def test_an_edit_records_the_state_it_leaves(release: FakeRelease) -> None:
    """Publishing is an edit, and the fake records it as one."""
    created = gh(["release", "create", RELEASE_TAG, "--draft"])
    assert created == 0, "the create must succeed"
    edited = gh(["release", "edit", RELEASE_TAG, "--draft=false"])
    assert edited == 0, "the edit must succeed"
    assert _state(release)["draft"] is False, _state(release)


def test_an_edit_ignores_a_flag_it_cannot_read(release: FakeRelease) -> None:
    """A value that is neither true nor false leaves the state unchanged."""
    created = gh(["release", "create", RELEASE_TAG, "--draft"])
    assert created == 0, "the create must succeed"
    edited = gh(["release", "edit", RELEASE_TAG, "--draft=perhaps"])
    assert edited == 0, "an unreadable flag must not fail the edit"
    assert _state(release)["draft"] is True, _state(release)


# -- curl --------------------------------------------------------------------


def _fetch_index(output: pathlib.Path, *extra: str) -> int:
    """Fetch the simple index into `output` with `extra` curl arguments."""
    arguments = ["--output", str(output), *extra, INDEX_URL]
    return curl(arguments)


def test_curl_serves_a_pep_691_index_of_what_pypi_holds(
    release: FakeRelease, tmp_path: pathlib.Path
) -> None:
    """The index names each file with the URL and digest PyPI would report."""
    (release.pypi / WHEEL).write_bytes(b"wheel")
    (release.pypi / SDIST).write_bytes(b"sdist")
    output = tmp_path / "index.json"
    assert _fetch_index(output) == 0, "the index fetch must succeed"
    index = json.loads(output.read_text(encoding="utf-8"))
    expected = list(itertools.starmap(_indexed, _HELD))
    assert index == {"name": "stilyagi", "files": expected}, index


def test_curl_reports_the_index_status_when_asked(
    release: FakeRelease, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--write-out`` receives the status, which the step retries on."""
    output = tmp_path / "index.json"
    completed = _fetch_index(output, "--write-out", "%{http_code}")
    assert completed == 0, "the fetch must succeed"
    assert capsys.readouterr().out == "200", "the status was not printed"


def test_curl_writes_an_empty_document_for_a_non_200_index(
    release: FakeRelease, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a 200 carries files; any other status writes a document to discard."""
    monkeypatch.setenv("FAKE_RELEASE_CURL_STATUSES", "404")
    output = tmp_path / "index.json"
    assert _fetch_index(output) == 0, "a non-200 still writes a document"
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written == {}, "a non-200 must carry no files"


def test_curl_repeats_the_last_scripted_status(
    release: FakeRelease, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry loop sees the scripted statuses in order, then the last one."""
    monkeypatch.setenv("FAKE_RELEASE_CURL_STATUSES", "000,200")
    output = tmp_path / "index.json"
    assert _fetch_index(output) == 7, "a 000 is curl's connection failure"
    assert _fetch_index(output) == 0, "the second attempt must succeed"
    assert _fetch_index(output) == 0, "the last status repeats for later attempts"


def test_curl_reads_the_output_path_from_its_short_option(
    release: FakeRelease, tmp_path: pathlib.Path
) -> None:
    """``-o`` names the destination exactly as ``--output`` does."""
    output = tmp_path / "index.json"
    completed = curl(["-o", str(output), INDEX_URL])
    assert completed == 0, "the short option must be read"
    index = json.loads(output.read_text(encoding="utf-8"))
    assert index["name"] == "stilyagi", index


def test_curl_fails_for_a_file_the_index_does_not_name(
    release: FakeRelease, tmp_path: pathlib.Path
) -> None:
    """``--fail`` exits 22 for a file PyPI does not hold, writing nothing."""
    output = tmp_path / "fetched.whl"
    completed = curl(["--output", str(output), f"{FILES_URL}{WHEEL}"])
    assert completed == 22, "a missing file must exit 22"
    assert not output.exists(), "nothing may be written for a missing file"


def test_curl_copies_a_file_the_index_names(
    release: FakeRelease, tmp_path: pathlib.Path
) -> None:
    """The published bytes are what the step's download receives."""
    (release.pypi / WHEEL).write_bytes(b"canonical")
    output = tmp_path / "fetched.whl"
    completed = curl(["--output", str(output), f"{FILES_URL}{WHEEL}"])
    assert completed == 0, "the download must succeed"
    assert output.read_bytes() == b"canonical", "the bytes differ"


def test_curl_prints_a_file_when_no_output_is_named(
    release: FakeRelease, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without ``--output`` the body goes to standard output, as curl's does."""
    (release.pypi / WHEEL).write_bytes(b"canonical")
    completed = curl([f"{FILES_URL}{WHEEL}"])
    assert completed == 0, "the file must be served"
    assert capsys.readouterr().out == "canonical", "the body was not printed"


# -- dispatch ----------------------------------------------------------------


def test_an_unused_subcommand_is_answered_without_side_effects(
    release: FakeRelease,
) -> None:
    """The fake serves the release commands; anything else succeeds and does nothing."""
    assert gh(["release", "list"]) == 0, "an unused subcommand must succeed"
    assert not (release.github / WHEEL).exists(), "an unused subcommand wrote an asset"


@pytest.mark.parametrize(
    ("argv", "program", "expected"),
    [
        (
            ["gh", "release", "view", RELEASE_TAG],
            "gh",
            ("release", "view", RELEASE_TAG),
        ),
        (["curl", INDEX_URL], "curl", (INDEX_URL,)),
    ],
    ids=["gh", "curl"],
)
def test_the_entry_point_journals_and_dispatches(
    release: FakeRelease,
    argv: cabc.Sequence[str],
    program: str,
    expected: tuple[str, ...],
) -> None:
    """A fake is found by its first argument, and every call is recorded."""
    main(argv)
    assert release.calls(program) == [expected], release.calls(program)
