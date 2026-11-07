"""The `cargo metadata` boundary that resolves the workspace member set.

`member_manifests` is the one lint-policy reader that leaves the filesystem:
it asks Cargo for the member set through `MetadataRunner`, a callable seam.
These cases pin both halves of that contract. The example cases pin the
selection and every malformed document shape, and the property case pins the
selection over arbitrary package order, arbitrary ID sets and arbitrary
overlap between the member list and the package list.

Every case injects a runner, so none of them reads or perturbs the
repository's real configuration.
"""

import json
import operator
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - builds fake `cargo metadata` outcomes, runs nothing.
import typing as typ

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.support import cargo_metadata
from tests.support.cargo_metadata import MetadataRunner, member_manifests
from tests.support.errors import ReadingError
from tests.support.reader_cases import assert_names_reader_and_path, write_text

if typ.TYPE_CHECKING:
    import collections.abc as cabc


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


def _manifest(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write an empty workspace manifest and return its path."""
    return write_text(tmp_path / "Cargo.toml", "[workspace]\nmembers = []\n")


def _assert_rejected(
    manifest: pathlib.Path, runner: MetadataRunner, message: str | None = None
) -> None:
    """Assert discovery rejects `manifest`, naming the reader and the path."""
    with pytest.raises(ReadingError, match=message) as raised:
        member_manifests(manifest, run_metadata=runner)
    assert_names_reader_and_path(raised, manifest)


def _timeout(*_args: object, **_kwargs: object) -> None:
    """Stand in for a Cargo that outlives its timeout."""
    raise subprocess.TimeoutExpired(["cargo", "metadata"], 1.0)


def _refuse(*_args: object, **_kwargs: object) -> None:
    """Stand in for a Cargo the platform refuses to execute."""
    raise OSError


def _undecodable(_path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Stand in for Cargo output that is not valid UTF-8."""
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


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
    path = write_text(tmp_path / "Cargo.toml", document)
    _assert_rejected(path, _returns(_completed("{}")))


def test_member_discovery_reads_the_runner_document(tmp_path: pathlib.Path) -> None:
    """Members come from the metadata document, not from the patterns."""
    manifest = _manifest(tmp_path)
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


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        pytest.param(
            _returns(_completed("", returncode=101, stderr="error: no network")),
            "no network",
            id="non-zero-exit",
        ),
        pytest.param(
            _returns(_completed("not json")), "invalid JSON", id="invalid-json"
        ),
        pytest.param(
            _returns(_completed("[]")), "non-object", id="non-object-document"
        ),
        pytest.param(_undecodable, "could not be decoded", id="undecodable"),
    ],
)
def test_member_discovery_reports_a_runner_failure(
    tmp_path: pathlib.Path, runner: MetadataRunner, message: str
) -> None:
    """Any document a runner reports badly is a reading finding."""
    _assert_rejected(_manifest(tmp_path), runner, message)


@pytest.mark.parametrize(
    ("run", "message"),
    [
        pytest.param(_timeout, "did not finish", id="timeout"),
        pytest.param(_refuse, "could not start", id="start-failure"),
    ],
)
def test_member_discovery_converts_a_process_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    run: cabc.Callable[..., None],
    message: str,
) -> None:
    """A Cargo that never starts or never returns is a reading finding."""
    monkeypatch.setattr(cargo_metadata.subprocess, "run", run)
    manifest = _manifest(tmp_path)
    with pytest.raises(ReadingError, match=message) as raised:
        member_manifests(manifest)
    assert_names_reader_and_path(raised, manifest)


def test_member_discovery_names_a_missing_cargo(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Cargo on `PATH` is a finding from the default runner, not a crash."""
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(cargo_metadata.shutil, "which", lambda _name: None)
    with pytest.raises(ReadingError, match="cargo is required") as raised:
        member_manifests(manifest)
    assert_names_reader_and_path(raised, manifest)


_PROBE_RECORD: typ.Final = {"id": "probe", "manifest_path": "/tree/probe/Cargo.toml"}


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"packages": []}, id="no-member-list"),
        pytest.param({"workspace_members": []}, id="no-package-list"),
        pytest.param(
            {"workspace_members": [1], "packages": []}, id="member-not-a-string"
        ),
        pytest.param(
            {"workspace_members": ["probe", "probe"], "packages": [_PROBE_RECORD]},
            id="member-listed-twice",
        ),
        pytest.param(
            {"workspace_members": ["probe"], "packages": ["probe"]},
            id="package-not-an-object",
        ),
        pytest.param(
            {"workspace_members": ["probe"], "packages": [{"manifest_path": "/x"}]},
            id="package-without-id",
        ),
        pytest.param(
            {"workspace_members": ["probe"], "packages": [{"id": "probe"}]},
            id="package-without-manifest-path",
        ),
        pytest.param(
            {
                "workspace_members": ["probe"],
                "packages": [{**_PROBE_RECORD, "manifest_path": 7}],
            },
            id="manifest-path-not-a-string",
        ),
        pytest.param(
            {"workspace_members": ["ghost"], "packages": [_PROBE_RECORD]},
            id="member-without-package",
        ),
        pytest.param(
            {
                "workspace_members": ["probe"],
                "packages": [_PROBE_RECORD, _PROBE_RECORD],
            },
            id="package-listed-twice",
        ),
    ],
)
def test_member_discovery_rejects_a_malformed_document(
    tmp_path: pathlib.Path, document: dict[str, object]
) -> None:
    """An untrustworthy metadata document is a finding, not a partial answer."""
    runner = _returns(_completed(json.dumps(document)))
    _assert_rejected(_manifest(tmp_path), runner)


#: A package identity that is safe as a single path segment.
PACKAGE_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=12,
)


@st.composite
def metadata_documents(draw: st.DrawFn) -> tuple[dict[str, object], set[str]]:
    """Draw a metadata document and the IDs it declares as members.

    The two lists are permuted independently, so neither the member list nor
    the package list is ordered relative to the other or to the sorted result.

    Returns
    -------
    tuple
        The metadata document, and the set of IDs it declares as members.
    """
    records = draw(
        st.lists(
            st.tuples(PACKAGE_ID, st.booleans()),
            min_size=0,
            max_size=6,
            unique_by=operator.itemgetter(0),
        )
    )
    packages = [
        {"id": identity, "manifest_path": f"/tree/{identity}/Cargo.toml"}
        for identity, _ in records
    ]
    members = {identity for identity, is_member in records if is_member}
    return {
        "workspace_members": list(draw(st.permutations(sorted(members)))),
        "packages": list(draw(st.permutations(packages))),
    }, members


# `deadline=None` because each example writes a manifest and parses a document;
# the elapsed time tracks filesystem and machine load rather than the code under
# test, and the default deadline fails under a loaded shared runner.
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=64,
    deadline=None,
)
@given(document=metadata_documents())
def test_member_discovery_selects_exactly_the_declared_ids(
    tmp_path: pathlib.Path,
    document: tuple[dict[str, object], set[str]],
) -> None:
    """Return exactly the declared members' manifests, in sorted order."""
    metadata, members = document
    manifest = _manifest(tmp_path)
    manifests = member_manifests(
        manifest, run_metadata=lambda _path: _completed(json.dumps(metadata))
    )
    expected = tuple(
        sorted(pathlib.Path(f"/tree/{identity}/Cargo.toml") for identity in members)
    )
    assert manifests == expected, (
        f"expected {expected} for members {sorted(members)}, got {manifests}"
    )
