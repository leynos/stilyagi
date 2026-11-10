"""Contract coverage for the failure channel the command shells share.

Every read-only command reports an expected operational failure the same way:
one `stilyagi <command>: <reason>` line on the error stream, and status two.
The shape is a contract rather than a coincidence -- a caller scripting against
`config`, `dump-ir`, or `clean` should be able to parse the prefix once -- so
the two helpers that state it are pinned here, and each command is driven far
enough to prove it reaches them rather than a private copy.

The status is asserted alongside the message on purpose. A command that
reported the right sentence but exited zero would look correct in a transcript
while telling a pipeline the run had succeeded.
"""

import io
import sys
import typing as typ

import pytest
from stilyagi import cli_clean, cli_command_shell, cli_config_command, cli_dump_ir
from stilyagi.cache.clean import CacheCleanResult
from stilyagi.cli_args import DumpIrOptions, _ConfigInspectionOptions
from stilyagi.cli_dump_ir import run_dump_ir
from stilyagi.config import path_resolution

from tests.config_resolution_support import _make_markdown_target

if typ.TYPE_CHECKING:
    import pathlib


class TestCommandStreams:
    """Both defaults are resolved in exactly one place."""

    def test_supplied_streams_are_returned_unchanged(self) -> None:
        """A caller-supplied stream is the one the command reports through."""
        out_sink = io.StringIO()
        error_sink = io.StringIO()

        streams = cli_command_shell.command_streams(out_sink, error_sink)

        assert streams.output is out_sink, (
            "expected the supplied result stream to be used as given"
        )
        assert streams.error is error_sink, (
            "expected the supplied failure stream to be used as given"
        )

    def test_missing_streams_fall_back_to_the_process_streams(self) -> None:
        """No supplied stream means the process's own standard streams."""
        streams = cli_command_shell.command_streams()

        assert streams.output is sys.stdout, (
            "expected the default result stream to be standard output"
        )
        assert streams.error is sys.stderr, (
            "expected the default failure stream to be standard error"
        )


class TestWriteCommandFailure:
    """One sentence shape and one status are stated once."""

    def test_the_sentence_names_the_subcommand_and_the_reason(self) -> None:
        """The line is `stilyagi <command>: <reason>` with a trailing newline."""
        sink = io.StringIO()

        status = cli_command_shell.write_command_failure(
            sink, command="clean", failure=OSError("permission denied")
        )

        assert status == 2, "expected the operational-failure status"
        assert sink.getvalue() == "stilyagi clean: permission denied\n", (
            "expected one command-prefixed line naming the failure"
        )

    def test_a_typed_failure_renders_its_own_message(self) -> None:
        """A typed error contributes its message, not a rendered type name."""
        sink = io.StringIO()

        cli_command_shell.write_command_failure(
            sink, command="config", failure=ValueError("unknown configuration key: x")
        )

        assert sink.getvalue() == "stilyagi config: unknown configuration key: x\n", (
            "expected the typed error's own message in the sentence"
        )


class TestCommandsShareTheChannel:
    """Each command reaches the shared channel rather than its own copy."""

    def test_clean_reports_a_failed_traversal_through_the_channel(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An unusable traversal root is reported once, prefixed and as status two."""
        # A file where a directory is expected makes the traversal fail with
        # the real `OSError` family rather than a simulated one.
        blocker = tmp_path / "cache-root"
        blocker.write_text("not a directory", encoding="utf-8")
        sink = io.StringIO()

        status = cli_clean.run_clean(root=blocker, output=io.StringIO(), error=sink)

        assert status == 2, "expected a failed traversal to exit two"
        assert sink.getvalue().startswith("stilyagi clean: "), (
            "expected the clean prefix on the reported failure"
        )

    def test_clean_reports_an_escaping_oserror_through_the_channel(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A traversal that raises is reported once, prefixed and as status two.

        The traversal test above exits through `_render_result`, because a
        failed subtree is collected into `result.errors` rather than raised.
        `run_clean`'s own `except OSError` branch is therefore unreached there,
        so it is driven here by making the traversal raise.
        """
        failure = "denied"
        error_sink = io.StringIO()

        def raise_denied(_root: pathlib.Path) -> typ.NoReturn:
            """Fail the traversal the way an unusable root does."""
            raise OSError(failure)

        monkeypatch.setattr(cli_clean, "clean_cache_tree", raise_denied)

        status = cli_clean.run_clean(
            root=tmp_path, output=io.StringIO(), error=error_sink
        )

        assert error_sink.getvalue() == f"stilyagi clean: {failure}\n", (
            "expected the shared helper's exact sentence on the error stream"
        )
        assert status == 2, "expected a raising traversal to exit two"

    def test_clean_renders_collected_failures_with_the_shared_prefix(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each collected traversal failure uses the shared prefix, not a copy."""
        collected = ("notes.md/one: denied", "notes.md/two: unstable")

        def return_collected(_root: pathlib.Path) -> CacheCleanResult:
            """Report two subtree failures without raising out of the traversal."""
            return CacheCleanResult(removed_files=0, errors=collected)

        monkeypatch.setattr(cli_clean, "clean_cache_tree", return_collected)
        error_sink = io.StringIO()

        status = cli_clean.run_clean(
            root=tmp_path, output=io.StringIO(), error=error_sink
        )

        assert error_sink.getvalue() == "".join(
            f"stilyagi clean: {failure}\n" for failure in collected
        ), "expected every collected failure to be rendered by the shared helper"
        assert status == 2, "expected collected failures to exit two"

    def test_dump_ir_reports_a_missing_target_through_the_channel(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing operand produces the dump-ir prefix and status two."""
        monkeypatch.chdir(tmp_path)
        sink = io.StringIO()

        status = run_dump_ir(
            DumpIrOptions(targets=("missing.md",)),
            collaborators=cli_dump_ir.DumpIrCollaborators(
                output=io.BytesIO(),
                error=sink,
            ),
        )

        assert status == 2, "expected a missing operand to exit two"
        assert sink.getvalue().startswith("stilyagi dump-ir: "), (
            "expected the dump-ir prefix on the reported failure"
        )

    def test_config_reports_a_missing_target_with_the_same_sentence(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Inspection reports the missing target through the shared channel."""
        missing = tmp_path / "missing.md"
        sink = io.StringIO()

        status = cli_config_command._run_config_inspection(
            _ConfigInspectionOptions(
                key=None,
                target=str(missing),
                output_format="json",
                explicit_config=(),
                isolated=False,
                select=(),
                ignore=(),
                extend_select=(),
            ),
            output=io.StringIO(),
            error=sink,
        )

        assert status == 2, "expected a missing target to exit two"
        assert (
            sink.getvalue() == f"stilyagi config: target does not exist: {missing}\n"
        ), "expected one config-prefixed line naming the target"


class TestInspectionTargetValidation:
    """The target check is a query, so its failures are values not writes."""

    def test_an_existing_file_is_returned(self, tmp_path: pathlib.Path) -> None:
        """A real file target passes through the query unchanged."""
        target = _make_markdown_target(tmp_path)

        resolved = cli_config_command._inspection_target(str(target))

        assert resolved == target, "expected the existing file to be returned"

    def test_an_existing_directory_is_returned(self, tmp_path: pathlib.Path) -> None:
        """A directory target is admissible for discovery-style inspection."""
        resolved = cli_config_command._inspection_target(str(tmp_path))

        assert resolved == tmp_path, "expected the existing directory to be returned"

    def test_a_missing_target_raises_the_named_reason(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A missing path raises rather than writing to a stream mid-query."""
        missing = tmp_path / "missing.md"

        with pytest.raises(cli_config_command._InspectionTargetError) as raised:
            cli_config_command._inspection_target(str(missing))

        assert str(raised.value) == f"target does not exist: {missing}", (
            "expected the missing-target sentence"
        )

    def test_an_unexpandable_target_raises_the_named_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The expansion failure keeps its own sentence."""

        def _unresolvable(path: pathlib.Path) -> pathlib.Path:
            """Fail every expansion the way an unset home directory would."""
            message = f"no home for {path}"
            raise path_resolution.PathResolutionError(message)

        monkeypatch.setattr(cli_config_command, "expand_user", _unresolvable)

        with pytest.raises(cli_config_command._InspectionTargetError) as raised:
            cli_config_command._inspection_target("~/notes.md")

        assert str(raised.value).startswith("cannot expand target: "), (
            "expected the expansion failure to keep its own sentence"
        )
