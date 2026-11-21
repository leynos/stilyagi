"""Specify the commands the release scripts run on the artefacts.

A release reaches its steady state through a short sequence of commands, and
this module specifies the half that decides PyPI's upload set: ``stage_pypi``
(in ``scripts/release_staging.py``) deletes what PyPI holds and replaces what
the Release holds, and ``write_output`` tells the workflow what remains. The
rules it dispatches over, and the ``State`` both halves share, are in
``scripts/release_assets.py``. The GitHub Release's half lives in
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
import release_staging
from release_assets import (
    PypiFile,
    ReleaseAssetError,
    Source,
    State,
)
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context
from tests.support.release_assets_fixtures import (
    digest,
    write_file,
    write_provenance,
)

if typ.TYPE_CHECKING:
    import pathlib

    from syrupy.assertion import SnapshotAssertion


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
        release_staging.stage_pypi(state, carried)


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
        release_staging.stage_pypi(state, carried, None)
    assert (publish / "c.whl").read_bytes() == b"rebuilt", (
        "the refusal must leave the artefact alone"
    )


def test_staging_pypi_leaves_only_what_pypi_lacks_and_says_so(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """A published name is deleted, and a carried one is replaced.

    PyPI holds ``a.whl`` and ``c.whl`` and the Release holds ``b.whl``, so the
    tag is complete across the two destinations and the release is not mixed:
    every name either PyPI or an earlier run's build already holds, and the one
    this run would send is the Release's signed bytes rather than its rebuild.
    ``b.whl`` is the only survivor, and it survives as the canonical bytes.
    """
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
        pypi={
            "a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a"),
            "c.whl": PypiFile(sha256=digest(publish / "c.whl"), url="https://x/c"),
        },
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_staging.stage_pypi(state, carried, records) is True, state
    assert release_assets.local_names(publish) == ["b.whl"], publish
    assert (publish / "b.whl").read_bytes() == b"canonical-b", publish
    notices = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::notice::")
    ]
    assert_with_context(
        notices == snapshot(extension_class=JSONSnapshotExtension),
        "expected each staged name to be reported with its disposition",
    )


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
    assert release_staging.stage_pypi(state, tmp_path) is False, state
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
    decided = release_assets.plan(
        release_assets.local_names(publish), state.pypi, state.github
    )
    assert decided.pypi_uploads == frozenset({"a.whl"}), decided


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
        pypi={
            "a.whl": PypiFile(sha256="whatever", url="https://x/a"),
            "c.whl": PypiFile(sha256="whatever", url="https://x/c"),
        },
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_staging.stage_pypi(state, carried, records) is True, state
    after_first = sorted(path.name for path in publish.iterdir())
    assert after_first == ["b.whl"], after_first
    # The second pass sees the same state and must leave the same survivors.
    second = State(
        publish=publish,
        pypi={
            "a.whl": PypiFile(sha256="whatever", url="https://x/a"),
            "c.whl": PypiFile(sha256="whatever", url="https://x/c"),
        },
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_staging.stage_pypi(second, carried, records) is True, second
    assert sorted(path.name for path in publish.iterdir()) == after_first, (
        sorted(path.name for path in publish.iterdir()),
        after_first,
    )
    assert (publish / "b.whl").read_bytes() == b"canonical-b", publish


def test_a_rebuild_beside_an_earlier_build_is_refused(tmp_path: pathlib.Path) -> None:
    """An interrupted upload cannot be completed from this run's rebuild.

    ``pypa/gh-action-pypi-publish`` uploads file by file, so an attempt that
    sent ``a.whl`` and then failed leaves PyPI holding one of the tag's names.
    A re-run that sent its own ``b.whl`` would leave PyPI holding two builds
    that never formed a pair, and no statement covers both. The re-run must
    refuse before the upload rather than pollute PyPI with bytes no run can
    ever replace.
    """
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"rebuilt-a")
    write_file(publish, "b.whl", b"rebuilt-b")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256="whatever", url="https://x/a")},
        github={},
    )
    with pytest.raises(ReleaseAssetError, match="refusing to add this run's rebuild"):
        release_staging.stage_pypi(state, tmp_path)
    assert release_assets.local_names(publish) == ["a.whl", "b.whl"], publish


def test_filling_the_gap_from_the_release_is_still_allowed(
    tmp_path: pathlib.Path,
) -> None:
    """The guard distinguishes the rebuild from the Release's signed bytes.

    This is the case the guard must not refuse, and it is why the rule is
    about the bytes' provenance rather than about how many names PyPI holds.
    PyPI holds ``a.whl`` and lacks ``b.whl``, exactly as an interrupted upload
    would leave it, but ``b.whl`` comes from the Release -- bytes an earlier
    run built and signed -- so the release is completed rather than mixed.
    """
    publish = tmp_path / "publish"
    carried = tmp_path / "github"
    write_file(publish, "a.whl", b"rebuilt-a")
    write_file(publish, "b.whl", b"rebuilt-b")
    write_file(carried, "b.whl", b"canonical-b")
    records = write_provenance(
        tmp_path / "records", {"b.whl": {"b.whl": b"canonical-b"}}
    )
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256="whatever", url="https://x/a")},
        github={"b.whl": digest(carried / "b.whl")},
    )
    assert release_staging.stage_pypi(state, carried, records) is True, state
    assert release_assets.local_names(publish) == ["b.whl"], publish
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
    decided = release_assets.plan(
        release_assets.local_names(publish), state.pypi, state.github
    )
    assert decided.canonical == {"a.whl": Source.PYPI}, decided
    assert not decided.pypi_uploads, decided
    assert not decided.github_uploads, decided
    assert release_assets.carryover(state) == ["a.whl"], state
