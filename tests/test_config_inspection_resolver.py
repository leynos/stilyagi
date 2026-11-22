"""Pin the resolver seam that keeps configuration inspection a query.

`_run_config_inspection` accepts a resolver instead of building one itself, so
a caller can observe the resolution through `cache_stats` and a test can drive
it with a double. The behaviour is worth its own module because the assertion
is about *which* collaborator ran, not about what it returned: a version that
constructed its own resolver would still produce identical output, and only a
recorded call distinguishes the two.

The module sits apart from `test_config_inspection.py` rather than lengthening
it past the repository's file-size ceiling.
"""

import typing as typ

from stilyagi import cli_config_command
from stilyagi.cli_args import _ConfigInspectionOptions
from stilyagi.config import ConfigResolver

from tests.config_resolution_support import _make_markdown_target

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    import pytest
    from stilyagi.config.inspection import _ConfigInspection


def test_inspection_queries_the_resolver_it_is_given(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drive the read-only query through an injected resolver, not a new one.

    Config inspection is a query: it must not reach for its own resolver
    mid-flight, or a caller could neither observe the resolution nor substitute
    one. Recording the call proves the collaborator the caller supplied is the
    one that ran.
    """
    target = _make_markdown_target(tmp_path)
    calls: list[pathlib.Path] = []

    class RecordingResolver(ConfigResolver):
        """Record each inspected target through the real resolution path."""

        def _inspect_config_for_path(
            self,
            target: pathlib.Path,
            *,
            cli_overrides: cabc.Mapping[str, object] | None,
            explicit_config: cabc.Iterable[str | pathlib.Path] | None,
            isolated: bool,
        ) -> _ConfigInspection:
            """Record one query, then resolve it through the real resolver."""
            calls.append(target)
            return super()._inspect_config_for_path(
                target,
                cli_overrides=cli_overrides,
                explicit_config=explicit_config,
                isolated=isolated,
            )

    options = _ConfigInspectionOptions(
        key="cache-dir",
        target=str(target),
        output_format="json",
        explicit_config=(),
        isolated=False,
        select=(),
        ignore=(),
        extend_select=(),
    )

    exit_code = cli_config_command._run_config_inspection(
        options,
        resolver=RecordingResolver(),
    )
    capsys.readouterr()

    assert exit_code == 0, "expected the injected resolver to drive a successful query"
    assert calls == [target], f"expected one query for {target}, recorded {calls}"
