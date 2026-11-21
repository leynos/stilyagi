"""Run one tag's whole release, then run the same tag again.

A tag's release is three jobs in sequence. ``draft-release`` creates the
Release and verifies what it already carries, ``publish-pypi`` decides the
upload set and sends it to PyPI, and ``publish-release`` fills the Release from
PyPI's bytes and publishes it. Every other release module runs one of those
jobs; none runs the three in order over one tag, and the tag is the unit issue
#229 states its requirement in.

So this module drives the workflow's own scripts for all three jobs, in the
workflow's order, against a scripted Release and PyPI. The harness that lays
the run out is ``tests.support.release_tag_to_release``; what a run must leave
behind is asserted here.

The re-run stages deliberately different bytes. A rebuild is never
byte-identical to the build before it, so a second run that took its own bytes
rather than the destinations' is visible here. Staging one payload twice would
hide the defect these tests exist for.
"""

import typing as typ

import pytest

from tests.support.release_github_workspace import (
    SDIST,
    WHEEL,
    published,
    record_state,
    uploads,
)
from tests.support.release_steps import requires_bash
from tests.support.release_tag_to_release import (
    BUNDLE,
    FIRST,
    NEW_RELEASE,
    SECOND,
    SECOND_BUNDLE,
    Tag,
    finish_tag,
    hold,
    holdings,
    publish_tag,
    stage_build,
)
from tests.support.release_workflow import github_output

pytest_plugins = ("tests.support.release_workspace_fixtures",)

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.release_fakes import FakeRelease
    from tests.support.release_workspace import Workspace


def first_release(
    work: pathlib.Path, fake: FakeRelease, *, tag: Tag = NEW_RELEASE
) -> tuple[str, ...]:
    """Run one tag end to end and assert it published.

    Both the first-release test and the re-run test need a tag that has
    already completed, so the run and its assertion are stated once. A re-run
    test whose first release did not publish would otherwise compare two
    states that were never the ones the requirement names.

    Parameters
    ----------
    work
        The job's working directory.
    fake
        The scripted destinations.
    tag
        The Release this run is for. It creates one by default, since a first
        release is what the run is.

    Returns
    -------
    tuple[str, ...]
        The names the PyPI transfer sent.
    """
    stage_build(work, fake, FIRST, BUNDLE)
    sent, transferred = publish_tag(work, fake, tag=tag)
    assert sent.returncode == 0, sent.stderr
    stage_build(work, fake, FIRST, BUNDLE)
    finished = finish_tag(work, fake, tag=tag)
    assert finished.returncode == 0, finished.stderr
    assert not published(fake)["draft"], "the first release must have published"
    return transferred


@requires_bash
@pytest.mark.parametrize(("prerelease", "expected"), [("false", False), ("true", True)])
def test_one_tag_run_leaves_both_destinations_holding_the_same_bytes(
    workspace: Workspace,
    prerelease: str,
    *,
    expected: bool,
) -> None:
    """The tag's own acceptance: PyPI and the Release agree, and it publishes.

    This is issue #229's first requirement stated at the level it is written:
    one tag, every artefact on PyPI, the same bytes on the Release, the
    provenance bundle beside them, and the Release published. No Release is
    seeded, so ``draft-release`` creates one rather than reusing it. The
    pre-release parameter is the value ``check-version`` derives from the tag,
    and it must reach the Release's published state.

    The byte comparison is not sharp here: on a first release the rebuild *is*
    what PyPI publishes, so taking the rebuild where a destination's bytes
    belong would agree with itself. It is sharp in the interrupted-tag test.
    """
    work, fake, _publish_dir = workspace
    tag = Tag(creates=True, prerelease=prerelease)
    transferred = first_release(work, fake, tag=tag)
    assert transferred == tuple(sorted((WHEEL, SDIST))), transferred
    assert github_output(work / "out-pypi")["remaining"] == "true", (
        "a first release leaves both artefacts for PyPI"
    )
    assert {path.name for path in fake.pypi.iterdir()} == {WHEEL, SDIST}, sorted(
        path.name for path in fake.pypi.iterdir()
    )
    assert {path.name for path in fake.github.iterdir()} == {
        WHEEL,
        SDIST,
        BUNDLE,
    }, sorted(path.name for path in fake.github.iterdir())
    for name in (WHEEL, SDIST):
        assert (fake.pypi / name).read_bytes() == (fake.github / name).read_bytes(), (
            f"the two destinations disagree about {name}"
        )
    assert published(fake) == {"draft": False, "prerelease": expected}, published(fake)


@requires_bash
def test_a_second_run_of_the_tag_uploads_nothing_to_either_destination(
    workspace: Workspace,
) -> None:
    """Issue #229's second requirement: the tag re-runs, and nothing is sent.

    The second build's bytes differ from everything already published, so a
    step that decided from its own rebuild rather than from the destinations
    would try to send them. It must not, and that is asserted directly on both
    channels: the PyPI transfer sends no name, and no ``gh release upload`` is
    made. PyPI keeps the bytes it published and the Release is given neither a
    second asset nor a second bundle.
    """
    work, fake, _publish_dir = workspace
    first_release(work, fake)
    before = holdings(fake)
    uploads_before = len(uploads(fake))

    stage_build(work, fake, SECOND, SECOND_BUNDLE)
    resent, transferred = publish_tag(work, fake)
    assert resent.returncode == 0, resent.stderr
    assert github_output(work / "out-pypi")["remaining"] == "false", (
        "a re-run must leave nothing for PyPI"
    )
    assert not transferred, transferred
    assert not any((work / "dist" / "publish").iterdir()), sorted(
        path.name for path in (work / "dist" / "publish").iterdir()
    )
    stage_build(work, fake, SECOND, SECOND_BUNDLE)
    finished = finish_tag(work, fake)
    assert finished.returncode == 0, finished.stderr
    assert not any((work / "github-upload").iterdir()), sorted(
        path.name for path in (work / "github-upload").iterdir()
    )
    assert len(uploads(fake)) == uploads_before, uploads(fake)[uploads_before:]
    assert holdings(fake) == before, "a re-run must change neither destination"
    assert published(fake) == {"draft": False, "prerelease": False}, published(fake)


@requires_bash
def test_a_pypi_hand_off_missing_a_name_keeps_the_release_a_draft(
    workspace: Workspace,
) -> None:
    """The release step refuses a PyPI index that lacks a name the tag built.

    ``publish-release`` runs only after ``publish-pypi`` succeeded, so a name
    PyPI does not list is a stale read rather than a new file. Here the upload
    really is incomplete -- the transfer sends the wheel and not the sdist --
    and the step must still refuse. Filling the Release's gap from this run's
    rebuild would attach bytes no run signed over, under a name the tag is
    about to publish, and an asset cannot be replaced.

    The Release therefore stays a draft and no upload carries the missing
    name, which is the failure this guard turns a silent mixed release into.
    A draft is seeded so that this asserts the state a run leaves behind rather
    than a Release the guard's own failure prevented from being created.
    """
    work, fake, _publish_dir = workspace
    record_state(fake, draft=True, prerelease=False)
    stage_build(work, fake, FIRST, BUNDLE)
    sent, transferred = publish_tag(work, fake, omit=(SDIST,))
    assert sent.returncode == 0, sent.stderr
    assert transferred == (WHEEL,), transferred

    stage_build(work, fake, FIRST, BUNDLE)
    finished = finish_tag(work, fake)
    assert finished.returncode == 1, finished.stdout
    assert SDIST in finished.stderr, finished.stderr
    assert SDIST not in {path.name for path in fake.github.iterdir()}, sorted(
        path.name for path in fake.github.iterdir()
    )
    assert published(fake)["draft"] is True, "a Release short of PyPI must not publish"


@requires_bash
def test_an_interrupted_tag_reaches_pypi_and_then_fails_at_the_release(
    workspace: Workspace,
) -> None:
    """A tag stopped between jobs is carried on, and stops where it cannot heal.

    PyPI holding the sdist while the Release holds the wheel is what an
    interrupted run leaves. ``publish-pypi`` cannot tell that from the
    legitimate sequence, so it completes and sends the Release's wheel; the
    release is then mixed rather than healed. ``publish-release`` refuses it:
    the Release holds no bundle covering the sdist it lacks, and a Release
    asset cannot be replaced.

    This asserts the limit ``adr-0015`` records rather than approving it. If
    staging ever distinguishes the two states, this test fails and the ADR,
    which says the recovery mechanism is unimplemented, needs revising with it.
    """
    work, fake, _publish_dir = workspace
    record_state(fake, draft=True, prerelease=False)
    hold(fake, {SDIST: b"published-sdist"}, {WHEEL: b"released-wheel"})
    stage_build(work, fake, SECOND, SECOND_BUNDLE)

    sent, _ = publish_tag(work, fake)
    assert sent.returncode == 0, sent.stderr
    assert (fake.pypi / WHEEL).read_bytes() == b"released-wheel", (
        "the carried wheel must reach PyPI as the Release's bytes"
    )

    stage_build(work, fake, SECOND, SECOND_BUNDLE)
    finished = finish_tag(work, fake)
    assert finished.returncode == 1, finished.stdout
    assert "provenance bundle" in finished.stderr, finished.stderr
    assert SDIST not in {path.name for path in fake.github.iterdir()}, sorted(
        path.name for path in fake.github.iterdir()
    )
    assert published(fake)["draft"] is True, "a mixed release must not be published"
