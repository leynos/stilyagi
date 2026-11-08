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

This module is standard-library only and is loaded only by the entry point a
fake re-executes (``tests/support/release_fake.py``), never by the test
session: importing it would pull this file into every fake invocation's import
graph for no benefit.
"""

import hashlib
import json
import os
import pathlib
import sys
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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


def verify(args: cabc.Sequence[str]) -> int:
    """Answer ``gh attestation verify`` for a local file.

    Like the real command, the artefact is looked up by its digest, so a file
    whose bytes no stored attestation names is refused however it is spelled.
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
    found = [record for record in _records() if _covers(record, _digest(artefact))]
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
