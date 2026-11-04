"""Hold the wheel-reading helpers to the metadata they accept and refuse.

``tests/test_maturin_build.py`` builds a wheel once and snapshots what maturin
wrote. That is the evidence the release needs, but it only ever reads a wheel
maturin built correctly: every refusal the reader declares — a missing
``WHEEL``, no generator, no ``Tag``, a dependency list that is not a list —
stays unexecuted, and a snapshot cannot tell a normalizer that preserved an
entry from one that quietly rewrote it.

This module supplies the other side. Each helper is called in process with a
small archive or a written-down metadata document, so the refusals are
constructed here rather than waited for, and the normalizations are asserted
against the strings a wheel actually carries rather than against the snapshot
they feed. The build itself, which writes, lives in
``tests/test_maturin_wheel_build_units.py`` beside the availability probes.

The functions are private to the module under test. They are imported
deliberately: a private helper that only its module's tests reach is exactly
what a unit test should name.
"""

import pathlib
import typing as typ
import zipfile

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from tests.test_maturin_build import (
    _DIST_INFO_SUFFIXES,
    _extract_wheel_line_fields,
    _header_value,
    _locate_dist_info_wheel,
    _normalize_wheel_entry,
    _normalize_wheel_tag,
    _object_mapping,
    _parse_metadata,
    _parse_wheel_header,
    _read_maturin_pins,
    _require_maturin_pin,
    _wheel_build_snapshot,
)

#: The repository root, named here rather than imported, because
#: ``_read_maturin_pins`` takes the root as an argument and a reader should see
#: which tree the test measures.
_REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[1]

#: A WHEEL document as maturin writes one, trimmed to the lines read here.
_WHEEL: typ.Final = (
    "Wheel-Version: 1.0\n"
    "Generator: maturin (1.9.4)\n"
    "Root-Is-Purelib: false\n"
    "Tag: cp314-cp314-manylinux_2_28_x86_64\n"
    "Tag: cp314-cp314-manylinux_2_28_aarch64\n"
)
#: A METADATA document, including one folded continuation line.
_METADATA: typ.Final = (
    "Metadata-Version: 2.4\n"
    "Name: stilyagi\n"
    "Version: 0.2.0\n"
    "Requires-Python: >=3.14\n"
    "Requires-Dist: typing-extensions\n"
    "Requires-Dist: annotated-doc\n"
    "Classifier: Programming Language :: Python :: 3.14\n"
    "Classifier: Programming Language :: Rust\n"
    "Summary: A tool\n"
    " that spans two lines\n"
)


def _write_wheel(path: pathlib.Path) -> pathlib.Path:
    """Write a minimal wheel archive at `path`, carrying both metadata files."""
    entries: list[tuple[str, bytes]] = [
        ("stilyagi/__init__.py", b""),
        ("stilyagi/_stilyagi_rs.cpython-314-x86_64-linux-gnu.so", b""),
        ("stilyagi-0.2.0.dist-info/RECORD", b""),
        ("stilyagi-0.2.0.dist-info/WHEEL", _WHEEL.encode("utf-8")),
        ("stilyagi-0.2.0.dist-info/METADATA", _METADATA.encode("utf-8")),
    ]
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return path


# -- _object_mapping and _require_maturin_pin --------------------------------


def test_a_toml_table_is_returned_unchanged() -> None:
    """The mapping is the table, not a copy, so callers may index it."""
    table = {"dev": ["maturin==1.9.4"]}
    assert _object_mapping(table) is table, "the table was copied"


def test_a_value_that_is_not_a_table_is_refused() -> None:
    """A list cannot be read as a TOML table, and its type is named."""
    with pytest.raises(TypeError, match="Expected TOML table, found list"):
        _object_mapping(["dev"])


@pytest.mark.parametrize(
    "dependencies",
    ["maturin==1.9.4", {"maturin==1.9.4": True}],
    ids=["scalar", "table"],
)
def test_a_dependency_list_that_is_not_a_list_is_refused(
    dependencies: object,
) -> None:
    """The refusal names the location, so a moved pin is findable."""
    with pytest.raises(TypeError, match=r"Expected dependency list at \[dev\]"):
        _require_maturin_pin(dependencies, "[dev]")


def test_a_pin_between_looser_constraints_is_found() -> None:
    """Entries that are not the exact pin are skipped rather than rejected."""
    dependencies: list[object] = [
        "other>=1",
        7,
        "maturin>=1.0",
        "maturin==1.9.4",
        "maturin==0.0.1",
    ]

    pin = _require_maturin_pin(dependencies, "[dev]")

    assert pin == "1.9.4", pin


def test_a_dependency_list_without_an_exact_pin_is_refused() -> None:
    """A range is not the pin the build must honour, and its absence is named."""
    with pytest.raises(
        AssertionError,
        match=r"Could not locate exact maturin dependency pin in \[dev\]",
    ):
        _require_maturin_pin(["maturin>=1.0", "maturin~=1.9"], "[dev]")


# -- metadata parsing --------------------------------------------------------


def test_the_repository_declares_one_pin_for_both_locations() -> None:
    """`_read_maturin_pins` reads the two tables the build reads, and agrees."""
    pins = _read_maturin_pins(_REPOSITORY_ROOT)

    dev = pins["[dependency-groups].dev"]
    assert pins == {
        "[dependency-groups].dev": dev,
        "[build-system].requires": dev,
    }, pins


def test_the_snapshot_metadata_is_reduced_to_the_reviewed_headers() -> None:
    """Unreviewed headers are dropped, and the reviewed ones are sorted."""
    parsed = _parse_metadata(_METADATA)

    assert sorted(parsed) == [
        "classifiers",
        "name",
        "requires_dist",
        "requires_python",
        "version",
    ], sorted(parsed)
    assert parsed["name"] == "stilyagi", parsed["name"]
    assert parsed["version"] == "0.2.0", parsed["version"]
    assert parsed["requires_python"] == ">=3.14", parsed["requires_python"]
    assert parsed["requires_dist"] == [
        "annotated-doc",
        "typing-extensions",
    ], parsed["requires_dist"]
    assert parsed["classifiers"] == [
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Rust",
    ], parsed["classifiers"]


def test_a_folded_header_continues_the_line_before_it() -> None:
    """A summary spanning two lines is joined, as the metadata grammar says."""
    headers = _headers(_METADATA.splitlines())

    assert headers["Summary"] == ["A tool that spans two lines"], headers["Summary"]


def test_a_body_after_the_headers_is_not_read_as_one() -> None:
    """The first line without a colon ends the header block."""
    headers = _headers(["Name: stilyagi", "", "Summary: not a header"])

    assert headers == {"Name": ["stilyagi"]}, headers


def test_a_header_that_is_absent_reads_as_nothing() -> None:
    """The empty answer is distinct from the empty string."""
    assert _header_value({}, "Name") is None, "an absent header must be None"


def test_a_header_is_read_from_the_first_occurrence() -> None:
    """A repeated header contributes its first value, not its last."""
    first = _header_value({"Name": ["first", "second"]}, "Name")

    assert first == "first", first


def _headers(lines: cabc.Sequence[str]) -> dict[str, list[str]]:
    """Reproduce the header scan `_parse_metadata` performs, for one question.

    `_parse_metadata` returns only the reviewed headers, and the folding and
    the end-of-headers rule are not visible through them, so the scan is
    repeated here over a document that keeps a header the snapshot drops.

    The parameter is a sequence rather than a list because `str.splitlines`
    answers with literal strings, and a `list` parameter would reject them.

    Parameters
    ----------
    lines
        The metadata document's lines, unfolded.

    Returns
    -------
    dict[str, list[str]]
        Each header and the values the scan accumulated for it.
    """
    headers: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith((" ", "\t")) and current is not None:
            headers[current][-1] = f"{headers[current][-1]} {line.strip()}"
            continue
        if ":" not in line:
            break
        current, _, value = line.partition(":")
        current = current.strip()
        headers.setdefault(current, []).append(value.strip())
    return headers


# -- entry and tag normalization --------------------------------------------


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            "stilyagi/_stilyagi_rs.cpython-314-x86_64-linux-gnu.so",
            "stilyagi/_stilyagi_rs.cpython-<platform>.<ext>",
        ),
        (
            "stilyagi/_stilyagi_rs.cpython-314-win_amd64.pyd",
            "stilyagi/_stilyagi_rs.cpython-<platform>.<ext>",
        ),
        (
            "stilyagi-0.2.0.dist-info/sboms/stilyagi.cyclonedx.json",
            "stilyagi-<version>.dist-info/sboms/<sbom>.cyclonedx.json",
        ),
    ],
    ids=["linux-so", "windows-pyd", "sbom"],
)
def test_a_version_or_platform_specific_entry_is_generalized(
    entry: str, expected: str
) -> None:
    """Every entry whose name carries a build-specific token is normalized."""
    normalized = _normalize_wheel_entry(entry)

    assert normalized == expected, normalized


def test_an_entry_the_snapshot_names_verbatim_is_left_alone() -> None:
    """A source file must keep its name: the snapshot is the file list."""
    normalized = _normalize_wheel_entry("stilyagi/__init__.py")

    assert normalized == "stilyagi/__init__.py", normalized


@pytest.mark.parametrize("suffix", sorted(_DIST_INFO_SUFFIXES))
def test_each_dist_info_member_is_normalized_through_its_suffix(suffix: str) -> None:
    """The suffix table is the only place a dist-info name is written down."""
    entry = f"stilyagi-0.2.0{suffix}"

    normalized = _normalize_wheel_entry(entry)

    assert normalized == _DIST_INFO_SUFFIXES[suffix], normalized


def test_a_wheel_tag_loses_only_its_platform() -> None:
    """The Python and ABI tags stay: they are the wheel's compatibility."""
    tag = _normalize_wheel_tag("cp314-cp314-manylinux_2_28_x86_64")

    assert tag == "cp314-cp314-<platform>", tag


def test_a_tag_with_a_platform_containing_hyphens_keeps_none_of_them() -> None:
    """Only the first two components are read; the rest is one platform."""
    tag = _normalize_wheel_tag("py3-none-any-extra")

    assert tag == "py3-none-<platform>", tag


# -- WHEEL parsing -----------------------------------------------------------


def test_the_generator_and_both_tags_are_read_from_a_wheel_document() -> None:
    """The generator is the maturin version, and every ``Tag`` line is kept."""
    generator, root_is_purelib, tags = _parse_wheel_header(
        _WHEEL, pathlib.Path("stilyagi-0.2.0-cp314-cp314-x86_64.whl")
    )

    assert generator == "1.9.4", generator
    assert root_is_purelib == "false", root_is_purelib
    assert tags == ["cp314-cp314-<platform>", "cp314-cp314-<platform>"], tags


def test_a_wheel_document_without_a_generator_is_refused() -> None:
    """The generator identifies the pinned maturin, so its absence is a fault."""
    with pytest.raises(
        AssertionError, match="Could not parse maturin generator from WHEEL metadata"
    ):
        _parse_wheel_header("Wheel-Version: 1.0\n", pathlib.Path("wheel.whl"))


def test_a_wheel_document_without_root_is_purelib_is_refused() -> None:
    """A missing purity flag cannot be guessed from the extension's presence."""
    payload = "Generator: maturin (1.9.4)\nTag: cp314-cp314-x86_64\n"

    with pytest.raises(AssertionError, match="Root-Is-Purelib"):
        _extract_wheel_line_fields(payload)


def test_a_wheel_document_without_a_tag_is_refused() -> None:
    """An untagged wheel cannot be matched to a platform, so it is refused."""
    payload = "Generator: maturin (1.9.4)\nRoot-Is-Purelib: false\n"

    with pytest.raises(AssertionError, match="Tag"):
        _extract_wheel_line_fields(payload)


def test_the_dist_info_wheel_entry_is_located_by_its_suffix() -> None:
    """The one ``.dist-info/WHEEL`` member is returned from the archive."""
    names = ["stilyagi/__init__.py", "stilyagi-0.2.0.dist-info/WHEEL"]

    located = _locate_dist_info_wheel(names)

    assert located == "stilyagi-0.2.0.dist-info/WHEEL", located


def test_a_wheel_archive_without_a_wheel_entry_is_refused() -> None:
    """A wheel that cannot describe itself is not one this suite can read."""
    with pytest.raises(AssertionError, match=r"wheel is missing \.dist-info/WHEEL"):
        _locate_dist_info_wheel(["stilyagi/__init__.py"])


# -- the archive read --------------------------------------------------------


def test_a_wheel_archive_is_reduced_to_the_snapshot_fields(
    tmp_path: pathlib.Path,
) -> None:
    """The snapshot is the generator, the reviewed headers and the file list."""
    wheel = _write_wheel(tmp_path / "stilyagi-0.2.0-cp314-cp314-x86_64.whl")

    snapshot = _wheel_build_snapshot(wheel)

    assert snapshot["generator"] == "1.9.4", snapshot["generator"]
    assert snapshot["wheel"] == {
        "root_is_purelib": "false",
        "tag": ["cp314-cp314-<platform>", "cp314-cp314-<platform>"],
    }, snapshot["wheel"]
    assert snapshot["entries"] == [
        "stilyagi-<version>.dist-info/METADATA",
        "stilyagi-<version>.dist-info/RECORD",
        "stilyagi-<version>.dist-info/WHEEL",
        "stilyagi/__init__.py",
        "stilyagi/_stilyagi_rs.cpython-<platform>.<ext>",
    ], snapshot["entries"]
