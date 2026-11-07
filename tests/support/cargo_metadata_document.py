"""Validate a `cargo metadata` document and select the workspace members.

`cargo metadata` is an external boundary, so its document is untrusted input:
a member list that is not a list of unique strings, a package record without a
string `id` or `manifest_path`, or a member with no matching package would
otherwise turn into a partial answer. Every check here rejects the whole
document with a `ReadingError` naming the reader and the requested path, so a
malformed document is a finding rather than a silently narrower member set.

The module is pure: it takes an already-parsed document and returns paths. The
command that produces the document, and the seam that lets tests inject one,
live in `tests.support.cargo_metadata`.
"""

import pathlib
import typing as typ

from tests.support.errors import ReadingError


def reject(path: pathlib.Path, message: str) -> typ.NoReturn:
    """Raise a `ReadingError` naming the reader and the requested path."""
    raise ReadingError(message, reader="lint_policy", path=str(path))


def string_list(value: object, path: pathlib.Path, what: str) -> list[str]:
    """Return `value` as a list of strings, or reject the document."""
    if not isinstance(value, list):
        reject(path, f"cargo metadata reported no {what}")
    if not all(isinstance(item, str) for item in value):
        reject(path, f"cargo metadata reported a non-string entry in the {what}")
    return value


def member_ids(metadata: dict[str, object], path: pathlib.Path) -> list[str]:
    """Return the document's workspace member IDs after validating them."""
    members = string_list(
        metadata.get("workspace_members"), path, "workspace member list"
    )
    if len(set(members)) != len(members):
        reject(path, "cargo metadata listed a workspace member twice")
    return members


def manifests_by_id(metadata: dict[str, object], path: pathlib.Path) -> dict[str, str]:
    """Return each package's manifest path, keyed by its package ID."""
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        reject(path, "cargo metadata reported no package list")
    records = [package_record(package, path) for package in packages]
    manifests = dict(records)
    if len(manifests) != len(records):
        reject(path, "cargo metadata reported a package twice")
    return manifests


def package_record(package: object, path: pathlib.Path) -> tuple[str, str]:
    """Return one package record's ID and manifest path, validated."""
    if not isinstance(package, dict):
        reject(path, f"package record {package!r} is not an object")
    return string_field(package, "id", path), string_field(
        package, "manifest_path", path
    )


def string_field(record: dict[str, object], field_name: str, path: pathlib.Path) -> str:
    """Return one string field of a package record, or reject the document."""
    value = record.get(field_name)
    if not isinstance(value, str):
        reject(path, f"package record has no string {field_name}: {value!r}")
    return value


def member_paths(
    metadata: dict[str, object], path: pathlib.Path
) -> tuple[pathlib.Path, ...]:
    """Return the manifest of every declared workspace member, sorted."""
    identities = member_ids(metadata, path)
    manifests = manifests_by_id(metadata, path)
    missing = [identity for identity in identities if identity not in manifests]
    if missing:
        reject(path, f"cargo metadata listed members without a package: {missing}")
    return tuple(sorted(pathlib.Path(manifests[identity]) for identity in identities))
