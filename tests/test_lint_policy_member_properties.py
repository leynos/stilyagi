"""Property tests for the resolved workspace member set.

`member_manifests` selects packages by the IDs Cargo reports as workspace
members and returns their manifests in sorted order. The example tests in
`tests/test_lint_policy_readers.py` pin the malformed-input and runner-failure
paths; these cases pin the selection itself over arbitrary package order,
arbitrary ID sets, and arbitrary overlap between the member list and the
package list.
"""

import json
import operator
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - builds fake `cargo metadata` outcomes, runs nothing.

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.support.cargo_metadata import member_manifests

#: A package identity that is safe as a single path segment.
PACKAGE_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=12,
)


@st.composite
def metadata_documents(draw: st.DrawFn) -> tuple[dict[str, object], set[str]]:
    """Draw a metadata document and the IDs it declares as members.

    The records are drawn in arbitrary order, so the package list and the
    member list are both unordered relative to the sorted result.

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
        "workspace_members": [record[0] for record in records if record[1]],
        "packages": packages,
    }, members


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    """Return a successful `cargo metadata` outcome reporting `stdout`."""
    return subprocess.CompletedProcess(
        args=["cargo", "metadata"], returncode=0, stdout=stdout, stderr=""
    )


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
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text("[workspace]\nmembers = []\n", encoding="utf-8")
    manifests = member_manifests(
        manifest, run_metadata=lambda _path: _completed(json.dumps(metadata))
    )
    expected = tuple(
        sorted(pathlib.Path(f"/tree/{identity}/Cargo.toml") for identity in members)
    )
    assert manifests == expected, (
        f"expected {expected} for members {sorted(members)}, got {manifests}"
    )
