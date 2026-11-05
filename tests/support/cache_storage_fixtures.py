"""Descriptors shared by the cache-storage contract modules.

The storage contracts split across two modules by subject — the primitives that
move bytes, and the ownership markers layered on top of them — but both need a
bare namespace descriptor to operate on. The fixture lives here so neither
module has to import from the other.
"""

import os
import typing as typ

import pytest
from stilyagi.cache import storage_primitives as primitives

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


@pytest.fixture
def namespace_fd(tmp_path: pathlib.Path) -> cabc.Iterator[int]:
    """Yield an open descriptor for one empty directory under ``tmp_path``."""
    namespace = tmp_path / "namespace"
    namespace.mkdir()
    descriptor = os.open(namespace, primitives._DIRECTORY_FLAGS)
    try:
        yield descriptor
    finally:
        os.close(descriptor)
