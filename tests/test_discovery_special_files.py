"""Discovery handling for filesystem entries that are not regular files."""

import os
import typing as typ

import pytest
from stilyagi import config, discovery

if typ.TYPE_CHECKING:
    import pathlib


def test_directory_discovery_skips_fifo_with_registered_suffix(
    tmp_path: pathlib.Path,
) -> None:
    """Never classify a non-regular filesystem entry as a source file."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("named pipes are not supported on this platform")

    root = tmp_path / "source"
    root.mkdir()
    fifo_path = root / "stream.py"
    os.mkfifo(fifo_path)

    result = discovery.discover_files_with_summary(
        [root], config.StilyagiConfig(respect_gitignore=False)
    )

    assert not result.files, "a FIFO with a registered suffix is not a source file"
    assert result.skipped_files == 1, "the unsupported entry contributes one skip"
    assert result.skipped_by_reason == (
        discovery.SkippedCandidateCount("unsupported_candidate_type", 1),
    ), "the unsupported filesystem kind uses its bounded skip reason"
