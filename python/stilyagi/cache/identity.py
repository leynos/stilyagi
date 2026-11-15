"""Fingerprint the extractor inputs that change what a cache entry means.

An entry is only reusable while everything that produced it is unchanged. Two
of those inputs are not part of a request's own text: the loaded Rust extension
binary, and the sources of the rule pack whose signatures are folded into the
key. Both are hashed here rather than in the extraction policy so the policy
reads as decisions about caching, not as filesystem walks.
"""

import hashlib
import pathlib
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = ["builtin_pack_signature", "native_extension_digest"]


def native_extension_digest() -> str:
    """Hash the loaded extension binary used by Rust extraction.

    Returns
    -------
    str
        The SHA-256 hex digest of the extension the process loaded.

    Raises
    ------
    OSError
        If the loaded extension reports no filesystem path, which leaves
        nothing to fingerprint.
    """
    import stilyagi._stilyagi_rs as bridge

    extension_filename = getattr(bridge, "__file__", None)
    if not isinstance(extension_filename, str):
        message = "loaded Rust extension has no filesystem path"
        raise OSError(message)
    extension_path = pathlib.Path(extension_filename)
    return hashlib.sha256(extension_path.read_bytes()).hexdigest()


def builtin_pack_signature(effective_config: cabc.Mapping[str, object]) -> str:
    """Hash enabled rule-package sources in stable relative-path order.

    Returns
    -------
    str
        The pack's SHA-256 hex digest, or ``"disabled"`` when the builtin pack
        is not configured.
    """
    configured_plugins = effective_config.get("plugins", ())
    if not isinstance(configured_plugins, (list, tuple)):
        return "disabled"
    if "builtin" not in configured_plugins:
        return "disabled"

    package_root = pathlib.Path(__file__).parent.parent / "rules"
    digest = hashlib.sha256()
    for source_file in sorted(package_root.rglob("*.py")):
        digest.update(source_file.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_file.read_bytes())
    return digest.hexdigest()
