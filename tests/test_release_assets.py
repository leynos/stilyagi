"""Specify the planning and comparison of ``scripts/release_assets.py``.

The module exists to answer three questions on a re-pushed tag: which bytes
are canonical for a name, which destination still lacks it, and whether the
two destinations ended up holding the same thing. The first two are pure
functions of sets, so they are property-tested over every overlap and
ordering rather than over a handful of examples. The third is checked against
real files, because a digest is a property of bytes and not of a name.

The staging commands — the ones that delete, copy and rewrite — are
``tests/test_release_assets_staging.py``'s subject; they are commands, and a
command needs a directory to run in.
"""

import json
import typing as typ

import pytest
import release_assets
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from release_assets import (
    Plan,
    ReleaseAssetError,
    Source,
    mismatches,
    plan,
)

from tests.support.release_assets_fixtures import (
    digest,
    write_assets,
    write_file,
    write_index,
)

if typ.TYPE_CHECKING:
    import pathlib

#: A handful of names is enough to exercise every overlap, and each example
#: stays cheap because the planning properties touch no filesystem.
NAMES: typ.Final = ("a.whl", "b.whl", "c.tar.gz", "d.sigstore.json")


# -- the planning properties -------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.sampled_from(NAMES), unique=True),
    st.lists(st.sampled_from(NAMES), unique=True),
    st.lists(st.sampled_from(NAMES), unique=True),
)
def test_every_name_takes_the_earliest_destination_that_holds_it(
    local: list[str],
    on_pypi: list[str],
    on_github: list[str],
) -> None:
    """PyPI outranks GitHub, and GitHub outranks this run's rebuilt bytes."""
    decided = plan(local, set(on_pypi), set(on_github))
    # The destinations are written out in precedence order here rather than
    # called from the module, so a change in that order fails the contract
    # instead of being echoed back by it.
    destinations = (
        (Source.PYPI, set(on_pypi)),
        (Source.GITHUB, set(on_github)),
    )
    for name in local:
        held = [source for source, names in destinations if name in names]
        assert decided.canonical[name] is (held[0] if held else Source.LOCAL), (
            name,
            on_pypi,
            on_github,
        )


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.sampled_from(NAMES), unique=True),
    st.lists(st.sampled_from(NAMES), unique=True),
    st.lists(st.sampled_from(NAMES), unique=True),
)
def test_each_destination_is_sent_exactly_the_names_it_lacks(
    local: list[str],
    on_pypi: list[str],
    on_github: list[str],
) -> None:
    """No destination is sent a name it holds, and none it does not need is left out."""
    decided = plan(local, set(on_pypi), set(on_github))
    assert decided.pypi_uploads == frozenset(local) - frozenset(on_pypi), decided
    assert decided.github_uploads == frozenset(local) - frozenset(on_github), decided


@settings(max_examples=40, deadline=None)
@given(st.lists(st.sampled_from(NAMES), unique=True))
def test_planning_is_order_insensitive(local: list[str]) -> None:
    """The rebuilt set is a set; the order it is discovered in means nothing."""
    forwards = plan(local, {NAMES[0]}, {local[0]} if local else set())
    backwards = plan(reversed(local), {NAMES[0]}, {local[0]} if local else set())
    assert forwards.canonical == backwards.canonical, (forwards, backwards)
    assert forwards.pypi_uploads == backwards.pypi_uploads, (forwards, backwards)
    assert forwards.github_uploads == backwards.github_uploads, (forwards, backwards)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.sampled_from(NAMES), unique=True))
def test_a_fully_published_name_needs_no_upload_anywhere(local: list[str]) -> None:
    """Both destinations holding every name is the re-run's steady state."""
    decided = plan(local, local, local)
    assert not decided.pypi_uploads, decided
    assert not decided.github_uploads, decided
    assert set(decided.canonical.values()) <= {Source.PYPI}, decided


def test_a_name_held_only_by_the_release_is_still_sent_to_pypi() -> None:
    """GitHub's bytes are canonical for a name PyPI has never seen."""
    decided = plan(["c.whl"], set(), {"c.whl"})
    assert decided.canonical == {"c.whl": Source.GITHUB}, decided
    assert decided.pypi_uploads == frozenset({"c.whl"}), decided
    assert decided.github_uploads == frozenset(), decided


def test_the_plan_is_immutable() -> None:
    """A plan is a value handed between steps, never a structure to mutate.

    The declaration is read rather than asserted by assigning to a field: a
    frozen, slotted class refuses that assignment at runtime, and a type
    checker sees the refusal too, so the contract is checked where the plan
    declares it instead of in a statement no checker would let through.
    """
    assert Plan.__dataclass_params__.frozen, "a plan must be frozen"
    assert "__slots__" in vars(Plan), "a plan must declare slots"


# -- the comparison properties -----------------------------------------------


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(st.sampled_from(NAMES), unique=True),
    st.dictionaries(
        st.sampled_from(NAMES), st.text(min_size=1, max_size=8), max_size=4
    ),
    st.dictionaries(
        st.sampled_from(NAMES),
        st.none() | st.text(min_size=1, max_size=8),
        max_size=4,
    ),
)
def test_a_name_is_reported_exactly_when_the_two_disagree(
    local: list[str],
    pypi: dict[str, str],
    github: dict[str, str | None],
) -> None:
    """The comparison is a per-name decision, not a global pass or fail."""
    reported = mismatches(local, pypi, github)
    expected = [
        name
        for name in sorted(set(local))
        if pypi.get(name) is None
        or github.get(name) is None
        or pypi[name] != github[name]
    ]
    assert [line.split()[0] for line in reported] == expected, reported


@settings(max_examples=40, deadline=None)
@given(st.lists(st.sampled_from(NAMES), unique=True))
def test_identical_digests_are_never_reported(local: list[str]) -> None:
    """Agreement, including on names with no local file, is silent."""
    digests = dict.fromkeys(local, "ab")
    assert mismatches(local, digests, dict(digests)) == [], local


def test_a_digest_github_omits_counts_as_a_disagreement() -> None:
    """``None`` is not a digest, so the presence of the name is not enough."""
    assert mismatches(["c.whl"], {"c.whl": "ab"}, {"c.whl": None}) == [
        "c.whl is missing from the GitHub Release or has no digest"
    ], "a missing digest must be named as a disagreement"


def test_a_differing_digest_names_both_values() -> None:
    """A disagreement must be actionable without re-reading either destination."""
    (line,) = mismatches(["c.whl"], {"c.whl": "aa"}, {"c.whl": "bb"})
    assert "aa" in line, line
    assert "bb" in line, line


# -- the index and asset readings --------------------------------------------


def test_the_index_reads_relative_urls_against_pypi(tmp_path: pathlib.Path) -> None:
    """A relative file URL is resolved against the project's simple index."""
    index = write_index({"c.whl": b"wheel"}, tmp_path)
    (file,) = release_assets.read_pypi_index(index).values()
    assert file.url == "https://pypi.org/packages/c.whl", file.url


def test_the_index_lowercases_thedigest(tmp_path: pathlib.Path) -> None:
    """Digest comparison must not fail on the case of a hex string."""
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps({
            "files": [
                {
                    "filename": "c.whl",
                    "url": "../../packages/c.whl",
                    "hashes": {"sha256": "AB"},
                }
            ]
        }),
        encoding="utf-8",
    )
    assert release_assets.read_pypi_index(path)["c.whl"].sha256 == "ab", path


def test_an_asset_without_a_sha256_digest_has_none(tmp_path: pathlib.Path) -> None:
    """A missing, malformed or foreign digest reads as unknown, not as a match."""
    path = write_assets({"a.whl": None, "b.whl": b"b"}, tmp_path)
    read = release_assets.read_github_assets(path)
    assert read["a.whl"] is None, read
    assert read["b.whl"] == digest(write_file(tmp_path, "b.whl", b"b")), read


def test_a_digest_in_another_algorithm_is_not_accepted(tmp_path: pathlib.Path) -> None:
    """Only ``sha256:`` is the comparison this module can make."""
    path = tmp_path / "assets.json"
    path.write_text(
        json.dumps({"assets": [{"name": "a.whl", "digest": "sha512:ab"}]}),
        encoding="utf-8",
    )
    assert release_assets.read_github_assets(path) == {"a.whl": None}, path


# -- the name safety boundary ------------------------------------------------


def test_an_unsafe_artefact_name_is_refused_before_anything_moves(
    tmp_path: pathlib.Path,
) -> None:
    """A name reaches a shell path and a TSV field, so it must be bounded.

    A name that a shell would read as an option, a name holding whitespace,
    and a name beginning with a dot are all refused. The list is checked in one
    example because ``local_names`` refuses the whole directory, not each name
    in turn: a single offender must stop the run.
    """
    directory = tmp_path / "artefacts"
    for name in ("a.whl", "-flag.whl", "sp ace.whl", ".hidden.whl"):
        write_file(directory, name, b"payload")
    with pytest.raises(ReleaseAssetError, match="unsafe artefact names"):
        release_assets.local_names(directory)


def test_a_directory_entry_that_is_not_a_file_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    """Staging a tree where a byte string belongs must fail before any copy."""
    directory = tmp_path / "artefacts"
    (directory / "nested.whl").mkdir(parents=True)
    write_file(directory, "a.whl", b"payload")
    with pytest.raises(ReleaseAssetError, match="unsafe artefact names"):
        release_assets.local_names(directory)


def test_the_artefact_names_are_sorted(tmp_path: pathlib.Path) -> None:
    """The listing is a reading, and its order is stable for a given set."""
    for name in ("b.whl", "a.whl", "c.tar.gz"):
        write_file(tmp_path, name, b"payload")
    assert release_assets.local_names(tmp_path) == ["a.whl", "b.whl", "c.tar.gz"], (
        tmp_path
    )
