"""Structural access to the ``[tool.duplication_gate]`` manifest table.

The allowlist's loader reads the manifest as plain data, while
``make duplication-allow`` edits it through tomlkit so existing formatting
survives. Both need one shared view of the table's shape: a scalar sitting
where a table or an array of tables belongs is a configuration defect, and it
must be reported in the gate's own vocabulary rather than escaping as an
``AttributeError`` from a chained ``setdefault``.

Updates are rendered back through tomlkit and replaced atomically, so a
rejected or failed edit leaves the original document byte-for-byte intact.
"""

import typing as typ

import tomlkit
import tomlkit.items
from atomic_write import AtomicWriteOptions, atomic_write
from nose_schema import GateConfigError

if typ.TYPE_CHECKING:
    import pathlib

#: A tomlkit table in either of its two spellings. The loader cannot tell an
#: inline table from a standard one before it inspects the value, and both
#: support the mapping protocol these helpers use.
type TableLike = tomlkit.items.Table | tomlkit.items.InlineTable


def _require_table(value: object, *, context: str) -> TableLike:
    """Reject a manifest value that is a scalar where a table belongs."""
    if not isinstance(value, (tomlkit.items.Table, tomlkit.items.InlineTable)):
        msg = f"{context} must be a table"
        raise GateConfigError(msg)
    return value


def sub_table(
    parent: tomlkit.TOMLDocument | TableLike,
    key: str,
    *,
    context: str,
    is_super: bool = False,
) -> TableLike:
    """Return the named sub-table of ``parent``, creating it only when absent.

    A document and a nested table share no declared supertype in tomlkit's
    API, so both are accepted. An existing value is validated before it is
    returned or descended into, so a malformed manifest is reported rather
    than half-mutated.

    Parameters
    ----------
    parent : tomlkit.TOMLDocument | TableLike
        Parsed document or table expected to hold ``key``.
    key : str
        Name of the sub-table to fetch or create.
    context : str
        Manifest path used in an invalid-value diagnostic.
    is_super : bool, optional
        Render a newly created table as a super-table, which the document's
        top level requires.

    Returns
    -------
    TableLike
        The existing or newly created table.
    """
    existing = parent.get(key)
    if existing is not None:
        return _require_table(existing, context=context)
    return parent.setdefault(key, tomlkit.table(is_super_table=is_super))


def raw_allow_entries(gate: TableLike) -> list[TableLike]:
    """Return the manifest's ``allow`` tables for inspection.

    The returned list is a snapshot holding the live entry tables, so updating
    a matched entry's ``reason`` edits the parsed document in place. Appending
    belongs to :func:`append_entry` instead, because an absent array must be
    created in the document rather than in this copy.

    Parameters
    ----------
    gate : TableLike
        Validated ``[tool.duplication_gate]`` table.

    Returns
    -------
    list[TableLike]
        The configured allow-entry tables, in file order.

    Raises
    ------
    GateConfigError
        If ``allow`` is present and is not an array of tables.
    """
    entries = gate.get("allow")
    if entries is None:
        return []
    if not isinstance(entries, tomlkit.items.AoT):
        msg = "pyproject.tool.duplication_gate.allow must be an array of tables"
        raise GateConfigError(msg)
    return list(entries)


def _entry_table(keys: tuple[str, ...], reason: str) -> tomlkit.items.Table:
    """Build the TOML table recording one reasoned allow entry."""
    entry = tomlkit.table()
    if len(keys) == 1:
        entry["unit"] = keys[0]
    else:
        entry["members"] = list(keys)
    entry["reason"] = reason
    return entry


def append_entry(gate: TableLike, *, keys: tuple[str, ...], reason: str) -> None:
    """Append one new allow entry, creating the ``allow`` array when absent.

    Parameters
    ----------
    gate : TableLike
        Validated ``[tool.duplication_gate]`` table to mutate.
    keys : tuple[str, ...]
        Location keys the entry covers; one key renders as ``unit`` and
        several render as ``members``.
    reason : str
        Reviewable justification recorded with the entry.
    """
    entries = gate.get("allow")
    if entries is None:
        entries = tomlkit.aot()
        gate["allow"] = entries
    entries.append(_entry_table(keys, reason))


def write_document(
    pyproject_path: pathlib.Path, document: tomlkit.TOMLDocument
) -> None:
    """Replace ``pyproject.toml`` atomically with the edited document.

    Parameters
    ----------
    pyproject_path : pathlib.Path
        Destination manifest; an existing file keeps its mode.
    document : tomlkit.TOMLDocument
        Parsed document to render and write.
    """
    atomic_write(
        pyproject_path,
        tomlkit.dumps(document).encode("utf-8"),
        options=AtomicWriteOptions(
            create_parents=False,
            preserve_mode=True,
            sync_file=True,
        ),
    )
