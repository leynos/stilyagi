"""Read provenance evidence and decide whether it attests an artefact.

Two documents answer the same question in different shapes. ``gh attestation
verify --format json`` answers with one record per attestation it checked,
whose statement lists every subject the attestation covers -- for this
repository the whole release, because one statement binds every wheel and the
sdist. A Sigstore bundle, which is what ``actions/attest-build-provenance``
hands the workflow and what the Release carries as an asset, holds that same
statement base64-encoded in its DSSE payload.

The statement is the evidence a destination is allowed to receive a file, so a
missing record, an unreadable one, or one whose subjects do not include the
name and digest is a refusal rather than a warning. This module only reads
files; the ``gh`` calls that produce them belong to the workflow.
"""

import base64
import binascii
import json
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

#: The DSSE payload type an in-toto statement carries.
_IN_TOTO_PAYLOAD = "application/vnd.in-toto+json"


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


def _decoded_payload(bundle: object) -> object:
    """Return the in-toto statement a parsed Sigstore bundle's payload holds."""
    envelope = bundle.get("dsseEnvelope") if isinstance(bundle, dict) else None
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, str):
        msg = "the bundle holds no DSSE payload"
        raise ProvenanceRecordError(msg)
    # Encoders are free to wrap base64 at any column, and the JSON field can
    # carry the newlines, so the whitespace is dropped before decoding.
    try:
        decoded = base64.b64decode("".join(payload.split()), validate=True)
        return json.loads(decoded)
    except (binascii.Error, ValueError) as error:
        msg = f"the bundle's DSSE payload is not base64 JSON: {error}"
        raise ProvenanceRecordError(msg) from error


def _bundle_documents(path: Path) -> list[object]:
    """Return the bundles a file holds, whether one object or JSON lines.

    ``actions/attest-build-provenance`` writes one JSON object. ``gh
    attestation download``, which is how an operator recovers the attestation
    for bytes a failed run published, writes JSON lines with one bundle per
    line. Accepting both is what makes the recovery instruction in the release
    refusals something an operator can actually carry out.

    Returns
    -------
    list[object]
        One parsed bundle per non-blank line, in file order.

    Raises
    ------
    ProvenanceRecordError
        If the file is unreadable or a non-blank line is not JSON.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        msg = f"cannot read the provenance bundle {path}: {error}"
        raise ProvenanceRecordError(msg) from error
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError as error:
        msg = f"the provenance bundle {path} is not JSON: {error}"
        raise ProvenanceRecordError(msg) from error


def read_bundle_statements(path: Path) -> list[object]:
    """Return every statement a bundle file holds, in the verifier's shape.

    ``actions/attest-build-provenance`` produces a Sigstore bundle, and the
    workflow stages it under a run-unique name and attaches it to the Release.
    Its statement is the same one the verifier prints, only still inside the
    DSSE envelope, so wrapping it in the verifier's own envelope lets one
    reader answer for both: what a statement covers does not depend on which
    document it was read out of.

    Parameters
    ----------
    path
        The bundle file to read: one Sigstore bundle, or JSON lines holding
        several.

    Returns
    -------
    list[object]
        One record per statement the file holds, parseable by
        ``has_matching_subject`` as the verifier's answer is.

    Raises
    ------
    ProvenanceRecordError
        If the file is unreadable, holds no bundle, or a bundle has no DSSE
        payload carrying an in-toto statement.
    """
    documents = _bundle_documents(path)
    if not documents:
        msg = f"the provenance bundle {path} holds no bundle"
        raise ProvenanceRecordError(msg)
    return [
        {"verificationResult": {"statement": _statement_of(document, path)}}
        for document in documents
    ]


def _statement_of(document: object, path: Path) -> dict[str, object]:
    """Return one bundle's decoded in-toto statement, or raise."""
    statement = _decoded_payload(document)
    if not isinstance(statement, dict):
        msg = f"the provenance bundle {path} holds no statement"
        raise ProvenanceRecordError(msg)
    envelope = document.get("dsseEnvelope") if isinstance(document, dict) else None
    payload_type = envelope.get("payloadType") if isinstance(envelope, dict) else None
    if payload_type != _IN_TOTO_PAYLOAD:
        msg = (
            f"the provenance bundle {path} carries payload type "
            f"{payload_type!r}, not {_IN_TOTO_PAYLOAD!r}"
        )
        raise ProvenanceRecordError(msg)
    return statement


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
