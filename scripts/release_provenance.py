"""Read the verifier's record and decide whether it attests an artefact.

``gh attestation verify --format json`` answers with one record per attestation
it checked. Each record's statement lists every subject the attestation covers,
which for this repository is the whole release: one statement binds every wheel
and the sdist, so verifying the sdist's bundle also establishes the wheels'.

The record is the evidence a destination is allowed to receive a file, so a
missing record, an unreadable one, or one whose subjects do not include the
name and digest is a refusal rather than a warning. This module only reads
files; the ``gh`` call that produces them belongs to the workflow.
"""

import json
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


class ProvenanceRecordError(Exception):
    """A provenance record is absent, unreadable, or attests something else."""


def read_provenance_record(path: Path) -> list[typ.Any] | None:
    """Return the verifier's records from ``path``; ``None`` when it is absent.

    Parameters
    ----------
    path
        The file a ``gh attestation verify --format json`` step wrote.

    Returns
    -------
    list[typing.Any] | None
        The records, or ``None`` when the step wrote no file. A file that
        exists but does not hold a JSON array of records raises.

    Raises
    ------
    ProvenanceRecordError
        If the file is present but is not a JSON array.
    """
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        msg = f"cannot read the provenance record {path}: {error}"
        raise ProvenanceRecordError(msg) from error
    if not isinstance(document, list):
        msg = f"the provenance record {path} is not a list of results"
        raise ProvenanceRecordError(msg)
    return document


def _subjects(record: object) -> list[object]:
    """Return one record's statement subjects, or none when it has no statement."""
    if not isinstance(record, dict):
        return []
    result = record.get("verificationResult")
    statement = result.get("statement") if isinstance(result, dict) else None
    subjects = statement.get("subject") if isinstance(statement, dict) else None
    return subjects if isinstance(subjects, list) else []


def _subject_matches(subject: object, name: str, digest: str) -> bool:
    """Return whether one subject names ``name`` under ``digest``."""
    if not isinstance(subject, dict):
        return False
    digests = subject.get("digest")
    recorded = digests.get("sha256") if isinstance(digests, dict) else None
    return (
        subject.get("name") == name
        and isinstance(recorded, str)
        and recorded.lower() == digest.lower()
    )


def has_matching_subject(
    records: cabc.Iterable[object], name: str, digest: str
) -> bool:
    """Return whether any record attests an artefact called ``name``.

    Parameters
    ----------
    records
        Records returned by ``read_provenance_record``.
    name
        The artefact name the destination is about to receive.
    digest
        The SHA-256 hex digest those bytes must hold.

    Returns
    -------
    bool
        Whether one record's statement lists exactly that name and digest.

    Examples
    --------
    >>> record = {"verificationResult": {"statement": {"subject": [
    ...     {"name": "a.whl", "digest": {"sha256": "AB"}},
    ... ]}}}
    >>> has_matching_subject([record], "a.whl", "ab")
    True
    >>> has_matching_subject([record], "a.whl", "cd")
    False
    """
    return any(
        _subject_matches(subject, name, digest)
        for record in records
        for subject in _subjects(record)
    )


def _source_digest(record: object) -> str | None:
    """Return one record's attested source commit, or ``None`` when it has none."""
    if not isinstance(record, dict):
        return None
    result = record.get("verificationResult")
    identity = result.get("verifiedIdentity") if isinstance(result, dict) else None
    commit = (
        identity.get("sourceRepositoryDigest") if isinstance(identity, dict) else None
    )
    return commit if isinstance(commit, str) and commit else None


def has_source_digest(records: cabc.Iterable[object], name: str, digest: str) -> bool:
    """Return whether a record attesting ``name`` also names a source commit.

    A signature proves *a* workflow produced the file. Naming the commit it
    built from is what makes the file attributable to a revision of this
    repository, and so worth attaching to a release nobody will rebuild.

    Parameters
    ----------
    records
        Records returned by ``read_provenance_record``.
    name
        The artefact name the destination is about to receive.
    digest
        The SHA-256 hex digest those bytes must hold.

    Returns
    -------
    bool
        Whether one record both attests those bytes and names a source commit.

    Examples
    --------
    >>> subject = {"name": "a.whl", "digest": {"sha256": "ab"}}
    >>> record = {
    ...     "verificationResult": {
    ...         "statement": {"subject": [subject]},
    ...         "verifiedIdentity": {"sourceRepositoryDigest": "a4089878"},
    ...     }
    ... }
    >>> has_source_digest([record], "a.whl", "ab")
    True
    >>> has_source_digest([record], "a.whl", "cd")
    False
    """
    return any(
        _source_digest(record) is not None
        and any(
            _subject_matches(subject, name, digest) for subject in _subjects(record)
        )
        for record in records
    )


def require_matching_record(
    record_dir: Path, name: str, digest: str, *, require_source: bool = False
) -> None:
    """Raise unless ``record_dir`` holds a record attesting ``name``'s bytes.

    Parameters
    ----------
    record_dir
        The directory holding one ``<asset>.json`` record per verified file.
    name
        The artefact name the destination is about to receive.
    digest
        The SHA-256 hex digest those bytes must hold.
    require_source
        Whether the record must also name the commit the file was built from.
        The PyPI job's carry does not ask, because the tag pin already fixes
        the revision; the Release job's does, because the file it attaches may
        have been built by any run of the tag.

    Raises
    ------
    ProvenanceRecordError
        If the record is absent, unreadable, does not attest this artefact, or
        is required to name a source commit and does not.
    """
    path = record_dir / f"{name}.json"
    records = read_provenance_record(path)
    if records is None:
        msg = f"no provenance record was written for {name}"
        raise ProvenanceRecordError(msg)
    if not has_matching_subject(records, name, digest):
        msg = f"no verified attestation covers {name} at sha256 {digest}"
        raise ProvenanceRecordError(msg)
    if require_source and not has_source_digest(records, name, digest):
        msg = f"the attestation for {name} names no source commit"
        raise ProvenanceRecordError(msg)
