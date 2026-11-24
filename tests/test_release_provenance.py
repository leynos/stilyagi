"""Specify the reading that decides whether a file may be carried.

``gh attestation verify --format json`` is the only thing that establishes
where a file came from, and its record is what the staging steps consult. The
record names every subject one attestation covers, so a single verified bundle
answers for the whole release.

The tests below are written against records shaped like the real verifier's
output, captured from ``leynos/cuprum``'s ``v0.2.0-beta2``: one record per
attestation, each with ``verificationResult.statement.subject`` listing the
artefact name and its ``sha256`` digest. A record that is absent, unreadable,
or that names something else must stop the carry rather than warn about it.
"""

import json
import typing as typ

import pytest
from release_provenance import (
    ProvenanceRecordError,
    has_matching_subject,
    read_provenance_record,
    require_matching_record,
)

if typ.TYPE_CHECKING:
    import pathlib

NAME: typ.Final = "stilyagi-0.2.0.tar.gz"
DIGEST: typ.Final = "bdc6ab92b1895613f7bfc35c762376f4830928add3d39061f7b3806d7aa422b4"
SOURCE: typ.Final = "a40898789a80e1ead3537cdab070fa87a80afced"


def _record(*subjects: tuple[str, str], source: str = "") -> dict[str, object]:
    """Return one verifier record attesting the given name and digest pairs.

    ``source`` writes the ``verifiedIdentity`` the verifier reports, which
    names the commit the attested workflow checked out. An empty value leaves
    that section out, as a verifier does for a revision it cannot attribute.

    Returns
    -------
    dict[str, object]
        One entry of the array ``gh attestation verify`` prints.
    """
    verification: dict[str, object] = {
        "statement": {
            "subject": [
                {"name": name, "digest": {"sha256": digest}}
                for name, digest in subjects
            ]
        }
    }
    if source:
        verification["verifiedIdentity"] = {"sourceRepositoryDigest": source}
    return {"verificationResult": verification}


def _write(directory: pathlib.Path, records: object, name: str = NAME) -> None:
    """Write ``records`` as the verifier's JSON answer for ``name``."""
    (directory / f"{name}.json").write_text(json.dumps(records), encoding="utf-8")


# -- reading the record ------------------------------------------------------


def test_an_absent_record_is_reported_as_absent(tmp_path: pathlib.Path) -> None:
    """A step that never ran, or died, must be distinguishable from a refusal."""
    assert read_provenance_record(tmp_path / "absent.json") is None, (
        "an absent record must read as absent, not as a refusal"
    )


def test_a_record_that_is_not_json_is_refused(tmp_path: pathlib.Path) -> None:
    """A truncated or empty file is not evidence that a signature failed."""
    path = tmp_path / "broken.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ProvenanceRecordError, match="cannot read"):
        read_provenance_record(path)


def test_a_record_that_is_not_a_list_is_refused(tmp_path: pathlib.Path) -> None:
    """``gh`` writes a JSON array; an object would silently yield no subjects."""
    path = tmp_path / "object.json"
    path.write_text('{"verificationResult": {}}', encoding="utf-8")
    with pytest.raises(ProvenanceRecordError, match="not a list"):
        read_provenance_record(path)


# -- matching a subject ------------------------------------------------------


def test_one_statement_answers_for_every_artefact_it_names() -> None:
    """The release's attestation binds every wheel and the sdist together."""
    records = [_record(("a.whl", "11"), (NAME, DIGEST), ("b.whl", "22"))]
    assert has_matching_subject(records, NAME, DIGEST), records
    assert has_matching_subject(records, "a.whl", "11"), records


def test_a_digest_mismatch_does_not_match() -> None:
    """The record must attest these bytes, not merely this filename."""
    records = [_record((NAME, DIGEST))]
    assert not has_matching_subject(records, NAME, "00" * 32), records


def test_a_digest_matches_regardless_of_case() -> None:
    """Hex digests are compared as values, so their case carries no meaning."""
    records = [_record((NAME, DIGEST.upper()))]
    assert has_matching_subject(records, NAME, DIGEST), records


def test_malformed_records_yield_no_match_rather_than_an_error() -> None:
    """An answer with no statement is a non-match, not a crash."""
    assert not has_matching_subject([{}], NAME, DIGEST), "empty record"
    assert not has_matching_subject(
        [{"verificationResult": {"statement": {"subject": "bad"}}}], NAME, DIGEST
    ), "subjects must be a list"


def test_a_malformed_record_does_not_mask_a_good_one() -> None:
    """One unparsable answer must not hide the attestation beside it."""
    records = [_record((NAME, DIGEST)), None]
    assert has_matching_subject(records, NAME, DIGEST), records


# -- requiring the record ----------------------------------------------------


def test_a_matching_record_permits_the_carry(tmp_path: pathlib.Path) -> None:
    """The happy path: a verified bundle that names this artefact exactly."""
    _write(tmp_path, [_record(("a.whl", "11"), (NAME, DIGEST))])
    require_matching_record(tmp_path, NAME, DIGEST)


def test_a_missing_record_refuses_the_carry(tmp_path: pathlib.Path) -> None:
    """Without a record there is no evidence, and none is not trusted."""
    with pytest.raises(ProvenanceRecordError, match="no provenance record"):
        require_matching_record(tmp_path, NAME, DIGEST)


def test_a_record_for_other_bytes_refuses_the_carry(tmp_path: pathlib.Path) -> None:
    """A rebuild passed off as the canonical file must not be carried."""
    _write(tmp_path, [_record((NAME, "00" * 32))])
    with pytest.raises(ProvenanceRecordError, match="no verified attestation"):
        require_matching_record(tmp_path, NAME, DIGEST)


# -- requiring the source commit ---------------------------------------------


def test_a_record_naming_its_source_commit_satisfies_the_stricter_carry(
    tmp_path: pathlib.Path,
) -> None:
    """The Release's direction asks for attribution, and a good record gives it."""
    _write(tmp_path, [_record((NAME, DIGEST), source=SOURCE)])
    require_matching_record(tmp_path, NAME, DIGEST, require_source=True)


def test_a_record_naming_no_source_commit_refuses_the_stricter_carry(
    tmp_path: pathlib.Path,
) -> None:
    """A signature alone does not say which revision the attached bytes are.

    The Release's asset is the one nobody rebuilds, so its record must name a
    commit even though the signature verified: otherwise a file carried from
    PyPI would be attributable only to *some* run of the workflow.
    """
    _write(tmp_path, [_record((NAME, DIGEST))])
    with pytest.raises(ProvenanceRecordError, match="names no source commit"):
        require_matching_record(tmp_path, NAME, DIGEST, require_source=True)


def test_a_bare_record_still_satisfies_the_carry_that_asks_no_source(
    tmp_path: pathlib.Path,
) -> None:
    """The PyPI direction pins the tag instead, so it must not demand a commit."""
    _write(tmp_path, [_record((NAME, DIGEST))])
    require_matching_record(tmp_path, NAME, DIGEST)
