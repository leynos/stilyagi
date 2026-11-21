"""Damage a Sigstore bundle in each of the two ways a release must refuse.

A bundle can be wrong in two independent respects, and the release checks them
in different places. Its *statement* can name bytes other than the ones being
published, which a decode alone catches; and its *signature* can fail to cover
its own statement, which only recomputing the signature catches. A test that
wanted the second would otherwise have to break the first as well, and would
then be refused by the coverage check before the signature was ever asked
about.

These helpers make one of those edits and leave the other intact, so a test
can state which refusal it is exercising rather than relying on the order the
checks happen to run in. Both are loaded only by test modules: they rewrite a
fixture's bytes in place, and nothing in the release scripts reads them.
"""

import base64
import hashlib
import json
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib


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


def edit_bundle_subjects(bundle: pathlib.Path, subjects: dict[str, bytes]) -> None:
    """Rewrite a bundle's subjects, leaving the signature that covered others.

    The signature is left exactly as it was while the payload is re-encoded
    over ``subjects``, so the result is what a tampered bundle looks like:
    well-formed, and self-consistent in every field except the one that
    establishes who said it. Recomputing over the statement it already carried
    would be no edit at all, which is why a caller passes bytes the bundle does
    not already attest.

    Parameters
    ----------
    bundle
        The bundle file to rewrite in place.
    subjects
        Each artefact name the edited statement will claim and the bytes it
        claims them to be.

    Raises
    ------
    ValueError
        If the rewrite also replaced the signature, which would leave a bundle
        that verifies and would make the caller's assertion pass for the wrong
        reason.
    """
    document = json.loads(bundle.read_text(encoding="utf-8"))
    envelope = document["dsseEnvelope"]
    signature = envelope["signatures"][0]["sig"]
    envelope["payload"] = base64.b64encode(
        json.dumps(_statement(subjects)).encode("utf-8")
    ).decode("ascii")
    if envelope["signatures"][0]["sig"] != signature:
        msg = "the signature was rewritten, so the bundle attests nothing"
        raise ValueError(msg)
    bundle.write_text(json.dumps(document), encoding="utf-8")


def break_bundle_signature(bundle: pathlib.Path) -> None:
    """Replace a bundle's signature, leaving the statement it covers intact.

    This is the bundle coverage alone cannot refuse: its statement names
    exactly the bytes it claims, so a check that reads the statement accepts
    it, and only recomputing the signature shows that nobody signed it.
    Breaking the signature rather than the statement is what isolates a
    pre-upload verification from the coverage question.

    Parameters
    ----------
    bundle
        The bundle file to rewrite in place.
    """
    document = json.loads(bundle.read_text(encoding="utf-8"))
    envelope = document["dsseEnvelope"]
    envelope["signatures"][0]["sig"] = f"sha256:{'0' * 64}"
    bundle.write_text(json.dumps(document), encoding="utf-8")


__all__ = ["break_bundle_signature", "edit_bundle_subjects"]
