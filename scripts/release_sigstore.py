"""Read the in-toto statements a Sigstore bundle carries.

``actions/attest-build-provenance`` produces a Sigstore bundle whose DSSE
payload is a base64-encoded in-toto statement, and ``gh attestation download``
writes the same bundles back as JSON lines. Both are how a Release records what
it published and how an operator recovers the attestation for bytes a failed
run left behind.

A statement is read back into the shape ``gh attestation verify --format json``
prints, so ``release_provenance`` can answer what a statement covers without
knowing which document it came out of. That separation is the point of this
module: decoding evidence and deciding admissibility are different concerns,
and only the second one belongs beside the carry's policy.

Like the other release modules, this one resolves no third-party code and makes
no network call: the workflow's ``gh`` steps fetch the bundles it reads.
"""

import base64
import binascii
import json
import typing as typ

from release_provenance import ProvenanceRecordError

if typ.TYPE_CHECKING:
    from pathlib import Path

#: The DSSE payload type an in-toto statement carries.
_IN_TOTO_PAYLOAD = "application/vnd.in-toto+json"


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
    payload_type = _payload_type(document)
    if payload_type != _IN_TOTO_PAYLOAD:
        msg = (
            f"the provenance bundle {path} carries payload type "
            f"{payload_type!r}, not {_IN_TOTO_PAYLOAD!r}"
        )
        raise ProvenanceRecordError(msg)
    return statement


def _payload_type(document: object) -> object:
    """Return a bundle's declared DSSE payload type, or ``None`` when absent."""
    envelope = document.get("dsseEnvelope") if isinstance(document, dict) else None
    return envelope.get("payloadType") if isinstance(envelope, dict) else None


__all__ = ["read_bundle_statements"]
