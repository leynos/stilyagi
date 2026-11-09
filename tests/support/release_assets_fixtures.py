"""Build the files the release scripts read, check, and copy.

The reconciliation modules read four things: a directory of rebuilt
artefacts, a PEP 691 JSON index of what PyPI holds, a ``gh release view
--json assets`` listing of what the release holds, and the provenance
evidence -- the per-asset records a verification step writes and the bundle a
run stages. Each is a file with a small, documented shape, and a test that
specifies a reading has to build that shape exactly -- including the parts a
hurried implementation might assume away, such as a relative file URL, an
asset with no digest, or a bundle that attests different bytes from the ones
being staged.

These helpers build those files from payloads, so a test states what each
destination holds in bytes and lets the digest follow. Names are written
verbatim; a caller that needs an unsafe name writes it itself.
"""

import base64
import hashlib
import json
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib


def digest(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes.

    Parameters
    ----------
    path
        The file to digest.

    Returns
    -------
    str
        The lowercase hex digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_file(directory: pathlib.Path, name: str, payload: bytes) -> pathlib.Path:
    """Write `payload` to ``directory``/`name`, creating the directory.

    Parameters
    ----------
    directory
        The directory to write into; created with its parents if absent.
    name
        The file name, written verbatim.
    payload
        The bytes to write.

    Returns
    -------
    pathlib.Path
        The path written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(payload)
    return target


def write_index(files: dict[str, bytes], directory: pathlib.Path) -> pathlib.Path:
    """Write a PEP 691 JSON index listing `files` with relative URLs.

    Parameters
    ----------
    files
        Each filename and the payload PyPI holds under it.
    directory
        The directory to write the index and payloads into.

    Returns
    -------
    pathlib.Path
        The index document written.
    """
    for name, payload in files.items():
        write_file(directory, name, payload)
    return _write_document(
        directory / "index.json",
        {
            "name": "stilyagi",
            "files": [
                {
                    "filename": name,
                    "url": f"../../packages/{name}",
                    "hashes": {"sha256": hashlib.sha256(payload).hexdigest()},
                }
                for name, payload in files.items()
            ],
        },
    )


def write_assets(
    assets: dict[str, bytes | None], directory: pathlib.Path
) -> pathlib.Path:
    """Write a ``gh release view --json assets`` document with digests.

    Parameters
    ----------
    assets
        Each asset name and its payload, or ``None`` for an asset GitHub
        reports without a digest.
    directory
        The directory to write the listing into.

    Returns
    -------
    pathlib.Path
        The listing document written.
    """
    return _write_document(
        directory / "assets.json",
        {
            "assets": [
                {
                    "name": name,
                    "digest": (
                        None
                        if payload is None
                        else f"sha256:{hashlib.sha256(payload).hexdigest()}"
                    ),
                }
                for name, payload in assets.items()
            ]
        },
    )


def _statement(subjects: dict[str, bytes]) -> dict[str, object]:
    """Return the in-toto statement naming every artefact by name and digest."""
    return {
        "subject": [
            {
                "name": name,
                "digest": {"sha256": hashlib.sha256(payload).hexdigest()},
            }
            for name, payload in subjects.items()
        ]
    }


def bundle_document(payload: str) -> dict[str, object]:
    """Return a Sigstore bundle whose envelope carries ``payload`` and its signature.

    The stand-in for ``gh attestation verify`` decides whether a bundle is
    signed exactly as the real command does, so the ``sig`` field has to be
    something it can recompute. Here it is a digest of the signed payload: a
    statement edited after it was signed no longer matches, which is the case
    the workflow's verify step exists to refuse.

    Parameters
    ----------
    payload
        The base64-encoded DSSE payload the envelope carries.

    Returns
    -------
    dict[str, object]
        A bundle in the shape ``actions/attest-build-provenance`` produces.
    """
    return {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {},
        "dsseEnvelope": {
            "payload": payload,
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": signature_of(payload), "keyid": ""}],
        },
    }


def signature_of(payload: str) -> str:
    """Return the signature this repository's fixtures sign ``payload`` with.

    Parameters
    ----------
    payload
        The base64-encoded DSSE payload the signature covers.

    Returns
    -------
    str
        The digest the stand-in verifier recomputes and compares.
    """
    return f"sha256:{hashlib.sha256(payload.encode('ascii')).hexdigest()}"


def _verifier_answer(
    subjects: dict[str, bytes], source: str
) -> list[dict[str, object]]:
    """Return the verifier's ``--format json`` answer for some artefacts.

    The answer is a list holding one entry per verified attestation, whose
    ``statement`` lists the artefacts signed together and whose
    ``verifiedIdentity`` names the commit the workflow checked out. Both the
    record a step writes and the bundle a run stages carry this shape, which
    is why they share one builder here.

    Returns
    -------
    list[dict[str, object]]
        The single verifier record covering every artefact in ``subjects``.
    """
    return [
        {
            "verificationResult": {
                "statement": _statement(subjects),
                "verifiedIdentity": {"sourceRepositoryDigest": source},
            }
        }
    ]


def write_provenance(
    directory: pathlib.Path,
    attestations: dict[str, dict[str, bytes]],
    *,
    source: str = "a40898789a80e1ead3537cdab070fa87a80afced",
) -> pathlib.Path:
    """Write verifier records attesting the given artefact bytes.

    Each record is written under the name of the artefact it answers for,
    which is how the workflow keeps one verified answer per downloaded file.
    One record may attest several artefacts, as the release's single
    attestation does for every wheel and the sdist.

    Parameters
    ----------
    directory
        The directory to write the records into.
    attestations
        Each record name, mapped to the artefacts it attests and the payload
        each was signed over.
    source
        The source commit the records name. ``""`` writes records that name
        none, which is what a verifier reports for an attestation built from
        a revision it cannot attribute.

    Returns
    -------
    pathlib.Path
        The directory the records were written into.
    """
    for record, subjects in attestations.items():
        _write_document(
            directory / f"{record}.json", _verifier_answer(subjects, source)
        )
    return directory


def write_bundle(
    directory: pathlib.Path,
    name: str,
    subjects: dict[str, bytes],
    *,
    source: str = "a40898789a80e1ead3537cdab070fa87a80afced",
) -> pathlib.Path:
    """Write one Sigstore bundle attesting ``subjects``.

    The bundle is what ``actions/attest-build-provenance`` produces: a Sigstore
    envelope whose DSSE payload is the base64-encoded in-toto statement naming
    each subject by name and digest. The workflow stages it under a
    run-unique ``<run>.sigstore.json`` name and attaches it to the Release, so
    both the staging and the post-publication check read this shape rather
    than the verifier's printed answer.

    Parameters
    ----------
    directory
        The directory to write the bundle into.
    name
        The bundle's file name, written verbatim and expected to end in
        ``.sigstore.json``.
    subjects
        Each artefact name the bundle attests and the payload it was signed
        over.
    source
        The source commit the bundle's statement names.

    Returns
    -------
    pathlib.Path
        The path of the bundle written.
    """
    statement = _statement(subjects)
    payload = base64.b64encode(json.dumps(statement).encode("utf-8")).decode("ascii")
    return _write_document(directory / name, bundle_document(payload))


def _write_document(path: pathlib.Path, document: object) -> pathlib.Path:
    """Serialize `document` as JSON to `path`, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


__all__ = [
    "bundle_document",
    "digest",
    "signature_of",
    "write_assets",
    "write_bundle",
    "write_file",
    "write_index",
    "write_provenance",
]
