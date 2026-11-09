"""The stand-in for ``gh attestation verify``.

The provenance checks in ``release.yml`` are what decide whether an artefact
may be carried from one destination to another, and they are shell steps that
run ``gh``. A test that executes one of those steps therefore needs an answer
from ``gh attestation verify`` it controls: one that looks a file up by the
digest of its bytes, as GitHub does, and then applies the policy flags to the
identity recorded in each matching attestation.

A record here has the shape ``gh attestation verify --format json`` prints: an
array of entries, each naming a statement (the subjects it covers) and a
``verifiedIdentity`` (who signed, from where, on what). Keeping that shape
faithful is what lets one piece of JSON serve as both the fake's answer and the
input a test writes, so the ``release_provenance`` module reads in a test what
it reads on a runner.

Two sources answer, and only one is consulted per invocation. Without
``--bundle`` the store is searched by the artefact's digest, as the real command
does when it queries GitHub. With ``--bundle`` the named file is the only
evidence: its signature is checked against the payload it covers, and a bundle
whose statement was edited after signing answers for nothing. That second path
is how the workflow checks the bundle attached to a Release, so a fake that fell
back to the store would let a tampered bundle pass on another record's strength.

This module is standard-library only and is loaded only by the entry point a
fake re-executes (``tests/support/release_fake.py``), never by the test
session: importing it would pull this file into every fake invocation's import
graph for no benefit.
"""

import base64
import binascii
import hashlib
import json
import os
import pathlib
import sys
import typing as typ

from tests.support.release_assets_fixtures import signature_of

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The identity the fixtures sign for, matching ``release.yml``'s policy.
_RELEASE_REPO: typ.Final = "leynos/stilyagi"
_RELEASE_REF: typ.Final = "refs/tags/v0.2.0"
_RELEASE_WORKFLOW: typ.Final = "/.github/workflows/release.yml"
_BUILD_COMMIT: typ.Final = "a40898789a80e1ead3537cdab070fa87a80afced"

#: The ``gh attestation`` options whose value is the next argument. Only the
#: ones the workflow passes are listed; an unlisted flag takes no value, so
#: the operand search steps over it and keeps walking.
_VALUED: typ.Final = frozenset({
    "--bundle",
    "--cert-identity",
    "--cert-identity-regex",
    "--cert-oidc-issuer",
    "--custom-trusted-root",
    "--digest-alg",
    "--format",
    "--hostname",
    "--jq",
    "--json",
    "--limit",
    "--owner",
    "--predicate-type",
    "--repo",
    "--signer-digest",
    "--signer-repo",
    "--signer-workflow",
    "--source-digest",
    "--source-ref",
    "--target",
})

#: The flag that makes the real command demand a GitHub-hosted runner.
_DENY_SELF_HOSTED: typ.Final = "--deny-self-hosted-runners"


def _store() -> pathlib.Path:
    """Return the directory standing in for the repository's attestation store."""
    return pathlib.Path(os.environ["FAKE_RELEASE_ATTESTATIONS"])


def _digest(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records() -> list[dict[str, object]]:
    """Return every attestation the store holds, one per stored record entry."""
    store = _store()
    if not store.is_dir():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(store.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, list):
            records.extend(entry for entry in document if isinstance(entry, dict))
    return records


def _statement(record: dict[str, object]) -> dict[str, object]:
    """Return one record's statement, or an empty mapping when it has none."""
    result = record.get("verificationResult")
    statement = result.get("statement") if isinstance(result, dict) else None
    return statement if isinstance(statement, dict) else {}


def _identity(record: dict[str, object]) -> dict[str, object]:
    """Return one record's verified identity, or an empty mapping."""
    result = record.get("verificationResult")
    identity = result.get("verifiedIdentity") if isinstance(result, dict) else None
    return identity if isinstance(identity, dict) else {}


def _subjects(record: dict[str, object]) -> list[object]:
    """Return one record's statement subjects, or none when it has none."""
    subjects = _statement(record).get("subject")
    return subjects if isinstance(subjects, list) else []


def _covers(record: dict[str, object], digest: str) -> bool:
    """Return whether one record's statement names an artefact by digest."""
    return any(
        isinstance(subject, dict)
        and isinstance(subject.get("digest"), dict)
        and subject["digest"].get("sha256", "").lower() == digest.lower()
        for subject in _subjects(record)
    )


def _option(args: cabc.Sequence[str], name: str) -> str | None:
    """Return one option's value, or ``None`` when it was not given."""
    return args[args.index(name) + 1] if name in args else None


def _operands(args: cabc.Sequence[str]) -> list[str]:
    """Return the arguments that are neither an option nor an option's value.

    ``--flag=value`` counts as one option; a bare ``--flag`` takes the next
    argument with it. What remains is an operand such as the artefact path.

    Returns
    -------
    list[str]
        The operands, in the order they were given.
    """
    operands: list[str] = []
    remaining = iter(args)
    for arg in remaining:
        if arg.startswith("-"):
            if arg in _VALUED:
                next(remaining, None)
            continue
        operands.append(arg)
    return operands


def _satisfies(record: dict[str, object], args: cabc.Sequence[str]) -> bool:
    """Return whether one record meets the policy the flags state.

    The fields are the ones ``gh attestation verify`` reads from the signing
    certificate: the repository the artefact is linked with, the workflow that
    signed it, the source ref and commit the workflow checked out, and the
    runner environment it ran on.

    Returns
    -------
    bool
        Whether every policy the flags state is met.
    """
    identity = _identity(record)
    checks: list[bool] = []
    repo = _option(args, "--repo")
    if repo is not None:
        checks.append(
            identity.get("sourceRepositoryURI") == f"https://github.com/{repo}"
        )
    signer = _option(args, "--signer-workflow")
    if signer is not None:
        checks.append(
            str(identity.get("subjectAlternativeName", "")).startswith(
                f"https://github.com/{signer}"
            )
        )
    ref = _option(args, "--source-ref")
    if ref is not None:
        checks.append(identity.get("sourceRepositoryRef") == ref)
    commit = _option(args, "--source-digest")
    if commit is not None:
        checks.append(identity.get("sourceRepositoryDigest") == commit)
    if _DENY_SELF_HOSTED in args:
        checks.append(identity.get("runnerEnvironment") == "github-hosted")
    return all(checks)


def _signed(payload: object, signature: object) -> bool:
    """Return whether a bundle's signature is the one its payload carries."""
    return (
        isinstance(payload, str)
        and isinstance(signature, str)
        and signature_of(payload) == signature
    )


def _bundle_signatures(document: object) -> list[object]:
    """Return the signature entries one parsed bundle's envelope holds."""
    envelope = document.get("dsseEnvelope") if isinstance(document, dict) else None
    signatures = envelope.get("signatures") if isinstance(envelope, dict) else None
    return signatures if isinstance(signatures, list) else []


def _bundle_payload(document: object) -> object:
    """Return one parsed bundle's base64 DSSE payload, or ``None`` when absent."""
    envelope = document.get("dsseEnvelope") if isinstance(document, dict) else None
    return envelope.get("payload") if isinstance(envelope, dict) else None


def _bundle_record(document: object) -> dict[str, object] | None:
    """Return the record a signed bundle vouches for, or ``None`` if unsigned.

    The identity fields are the ones ``gh attestation verify --bundle`` reads
    from the signing certificate; the fake's fixtures sign for this
    repository's release workflow at the tag, which is the policy the workflow
    states.

    Returns
    -------
    dict[str, object] | None
        The verified record, or ``None`` when no signature covers the payload.
    """
    payload = _bundle_payload(document)
    if not any(
        _signed(payload, entry.get("sig"))
        for entry in _bundle_signatures(document)
        if isinstance(entry, dict)
    ):
        return None
    try:
        decoded = base64.b64decode("".join(str(payload).split()), validate=True)
        statement = json.loads(decoded)
    except binascii.Error, ValueError:
        return None
    if not isinstance(statement, dict):
        return None
    return {
        "verificationResult": {
            "statement": statement,
            "verifiedIdentity": {
                "sourceRepositoryURI": f"https://github.com/{_RELEASE_REPO}",
                "sourceRepositoryRef": _RELEASE_REF,
                "sourceRepositoryDigest": _BUILD_COMMIT,
                "subjectAlternativeName": (
                    f"https://github.com/{_RELEASE_REPO}{_RELEASE_WORKFLOW}"
                    f"@{_RELEASE_REF}"
                ),
                "runnerEnvironment": "github-hosted",
            },
        }
    }


def _bundle_records(path: pathlib.Path) -> list[dict[str, object]]:
    """Return the records one on-disk bundle vouches for, or none if unsigned.

    ``--bundle`` names a file the caller already holds, so the answer depends
    on that file alone: its statement supplies the subjects, but only a bundle
    whose signature covers that statement vouches for it. A statement edited
    after signing leaves no record, which is what the real command reports.

    Returns
    -------
    list[dict[str, object]]
        One record per signed bundle in the file, empty when none verifies.
    """
    try:
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        documents = [json.loads(line) for line in lines]
    except (OSError, ValueError) as error:
        print(f"cannot read the bundle {path}: {error}", file=sys.stderr)
        return []
    records = [_bundle_record(document) for document in documents]
    return [record for record in records if record is not None]


def _records_for(args: cabc.Sequence[str]) -> list[dict[str, object]]:
    """Return the records that answer for the artefact under the given flags."""
    bundle = _option(args, "--bundle")
    if bundle is not None:
        return _bundle_records(pathlib.Path(bundle))
    return _records()


def verify(args: cabc.Sequence[str]) -> int:
    """Answer ``gh attestation verify`` for a local file.

    Like the real command, the artefact is looked up by its digest, so a file
    whose bytes no stored attestation names is refused however it is spelled.
    When ``--bundle`` names a file, that file is the only evidence consulted:
    a bundle verified offline must not consult the store, or a bundle whose
    signature does not hold would pass on the strength of a different record.
    The policy flags are then applied to the signing identity, and only the
    records that satisfy all of them are reported.

    Parameters
    ----------
    args
        The argument vector after ``attestation verify``.

    Returns
    -------
    int
        ``0`` when at least one record met the policy, ``1`` otherwise.
    """
    operands = _operands(args)
    if not operands:
        print("no path was given for a file to verify", file=sys.stderr)
        return 1
    artefact = pathlib.Path(operands[0])
    found = [
        record for record in _records_for(args) if _covers(record, _digest(artefact))
    ]
    if not found:
        print(f"no attestations found for {artefact.name}", file=sys.stderr)
        return 1
    accepted = [record for record in found if _satisfies(record, args)]
    if not accepted:
        print("no attestations matched the policy", file=sys.stderr)
        return 1
    if _option(args, "--format") == "json":
        print(json.dumps(accepted))
    else:
        print(f"Verified {len(accepted)} attestation(s) for {artefact.name}")
    return 0


__all__ = ["verify"]
