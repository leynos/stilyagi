"""Specify the commands ``scripts/release_assets.py`` runs on the artefacts.

A release reaches its steady state through a short sequence of commands, and
this module specifies the half that decides PyPI's upload set: ``stage_pypi``
deletes what PyPI holds and replaces what the Release holds, and ``write_output``
tells the workflow what remains. The GitHub Release's half lives in
``test_release_github_upload.py``.

The running theme is that a command must be safe to run twice. A re-pushed tag
runs the whole sequence again against destinations that already hold almost
everything, so every stage must be a no-op where there is nothing to do, and
must refuse — not proceed — where the bytes it was promised are not the bytes
it has.
"""

import typing as typ

import pytest
import release_assets
from release_assets import (
    PypiFile,
    ReleaseAssetError,
    Source,
    State,
)

from tests.support.release_assets_fixtures import (
    digest,
    write_file,
    write_provenance,
)

if typ.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def output_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    """Point ``GITHUB_OUTPUT`` at a scratch file and return its path."""
    path = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


# -- staging for PyPI --------------------------------------------------------


def test_a_carried_file_with_the_wrong_bytes_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    """A release asset edited after its digest was recorded must not be sent on."""
    publish = tmp_path / "publish"
    carried = tmp_path / "github"
    write_file(publish, "c.whl", b"rebuilt")
    write_file(carried, "c.whl", b"tampered")
    state = State(publish=publish, pypi={}, github={"c.whl": digest(carried / "c.whl")})
    (carried / "c.whl").write_bytes(b"changed-after-the-fact")
    with pytest.raises(ReleaseAssetError, match="expected"):
        release_assets.stage_pypi(state, carried)


def test_a_carried_file_with_no_records_at_all_is_not_sent_on(
    tmp_path: pathlib.Path,
) -> None:
    """A job that verified nothing supplies no directory, and that is a refusal.

    The digest check above cannot stand in for this one: bytes that match the
    Release's listing are still unattributed, and copying them would make the
    PyPI upload rest on the API's word alone. ``None`` is what
    ``release_assets_cli`` passes when the provenance directory was never
    given, so this is the shape a skipped verification step takes.
    """
    publish = tmp_path / "publish"
    carried = tmp_path / "github"
    write_file(publish, "c.whl", b"rebuilt")
    write_file(carried, "c.whl", b"canonical")
    state = State(publish=publish, pypi={}, github={"c.whl": digest(carried / "c.whl")})
    with pytest.raises(ReleaseAssetError, match="no provenance record was supplied"):
        release_assets.stage_pypi(state, carried, None)
    assert (publish / "c.whl").read_bytes() == b"rebuilt", (
        "the refusal must leave the artefact alone"
    )


def test_staging_pypi_leaves_only_what_pypi_lacks_and_says_so(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A published name is deleted, a carried name is replaced, the rest stays."""
    publish = tmp_path / "publish"
    carried = tmp_path / "github"
    write_file(publish, "a.whl", b"rebuilt-a")
    write_file(publish, "b.whl", b"rebuilt-b")
    write_file(publish, "c.whl", b"rebuilt-c")
    write_file(carried, "b.whl", b"canonical-b")
    records = write_provenance(
        tmp_path / "records", {"b.whl": {"b.whl": b"canonical-b"}}
    )
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_assets.stage_pypi(state, carried, records) is True, state
    assert release_assets.local_names(publish) == ["b.whl", "c.whl"], publish
    assert (publish / "b.whl").read_bytes() == b"canonical-b", publish
    notices = capsys.readouterr().out
    assert "Skipping a.whl" in notices, notices
    assert "GitHub Release's bytes for b.whl" in notices, notices


def test_staging_pypi_reports_that_nothing_remains(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fully published tag reaches PyPI's upload step with an empty set."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={},
    )
    assert release_assets.stage_pypi(state, tmp_path) is False, state
    assert "nothing to publish" in capsys.readouterr().out, (
        "an empty upload set must be reported"
    )


# -- state, outputs, and the plan -------------------------------------------


def test_state_loads_an_absent_index_as_an_empty_one(tmp_path: pathlib.Path) -> None:
    """A project PyPI has never seen has no index, and that is not a failure."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    listing = tmp_path / "assets.json"
    listing.write_text('{"assets": []}', encoding="utf-8")
    state = State.load(publish, None, listing)
    assert not state.pypi, state
    assert not state.github, state
    assert state.plan().pypi_uploads == frozenset({"a.whl"}), state


def test_the_step_output_is_written_lowercase(output_file: pathlib.Path) -> None:
    """GitHub compares the output with a quoted ``'true'``, so the case matters."""
    release_assets.write_output("pending", value=True)
    release_assets.write_output("remaining", value=False)
    written = output_file.read_text(encoding="utf-8")
    assert written == "pending=true\nremaining=false\n", written


# -- the reconciliation is idempotent ----------------------------------------


def test_staging_the_same_state_twice_changes_nothing(tmp_path: pathlib.Path) -> None:
    """A stage is a command, and running it twice is running it once."""
    publish = tmp_path / "publish"
    carried = tmp_path / "github"
    write_file(publish, "a.whl", b"rebuilt-a")
    write_file(publish, "b.whl", b"rebuilt-b")
    write_file(publish, "c.whl", b"rebuilt-c")
    write_file(carried, "b.whl", b"canonical-b")
    records = write_provenance(
        tmp_path / "records", {"b.whl": {"b.whl": b"canonical-b"}}
    )
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256="whatever", url="https://x/a")},
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_assets.stage_pypi(state, carried, records) is True, state
    after_first = sorted(path.name for path in publish.iterdir())
    assert after_first == ["b.whl", "c.whl"], after_first
    # The second pass sees the same state and must leave the same survivors.
    assert release_assets.stage_pypi(state, carried, records) is True, state
    assert sorted(path.name for path in publish.iterdir()) == after_first, (
        sorted(path.name for path in publish.iterdir()),
        after_first,
    )
    assert (publish / "b.whl").read_bytes() == b"canonical-b", publish


def test_a_release_that_agrees_plans_nothing_on_a_second_run(
    tmp_path: pathlib.Path,
) -> None:
    """The published steady state is the fixed point every stage must reach."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={"a.whl": digest(publish / "a.whl")},
    )
    decided = state.plan()
    assert decided.canonical == {"a.whl": Source.PYPI}, decided
    assert not decided.pypi_uploads, decided
    assert not decided.github_uploads, decided
    assert release_assets.carryover(state) == ["a.whl"], state
