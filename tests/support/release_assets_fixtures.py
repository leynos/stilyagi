"""Build the files ``scripts/release_assets.py`` reads and digests.

The reconciliation module reads three things: a directory of rebuilt
artefacts, a PEP 691 JSON index of what PyPI holds, and a ``gh release view
--json assets`` listing of what the release holds. Each is a file with a
small, documented shape, and a test that specifies a reading has to build
that shape exactly — including the parts a hurried implementation might
assume away, such as a relative file URL or an asset with no digest.

These helpers build those files from payloads, so a test states what each
destination holds in bytes and lets the digest follow. Names are written
verbatim; a caller that needs an unsafe name writes it itself.
"""

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


def _write_document(path: pathlib.Path, document: object) -> pathlib.Path:
    """Serialize `document` as JSON to `path`, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


__all__ = ["digest", "write_assets", "write_file", "write_index"]
