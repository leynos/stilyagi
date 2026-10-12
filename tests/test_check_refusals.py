"""Command-boundary coverage for a write a mutating run refused to make.

The classes here pin the same subject from two directions: a write the run
declined to perform, and how that refusal reaches the user. One direction is an
environment fault -- the filesystem said no -- and the other is a planning
decision -- the target changed after it was planned. The documented contract
separates them by exit status, `2` and `1` respectively, and that difference is
only meaningful because each refusal is reported rather than raised. Both
directions are pinned in text and in JSON, because a machine consumer reads the
JSON document and never the prose.

Every test here describes a run that changed nothing, because a refusal always
leaves its target alone. That is what routes each of them through
`print_unmodified_report`. The other reporter -- the one a run reaches only by
writing *some* file and refusing another -- is covered in
`tests/test_check_partial_runs.py`. The rest of the mutating path, and the exit
status when files were written and diagnostics remain, live in
`tests/test_check_mutation.py`; the non-mutating command boundaries live in
`tests/test_check_boundaries.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_refusals.py
"""

import io
import pathlib
import typing as typ

from stilyagi import cli

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import rewrite_paragraph

if typ.TYPE_CHECKING:
    import pytest


def refuse_replace(
    _self: object, _target: object, *_args: object, **_kwargs: object
) -> None:
    """Refuse the swap the way a read-only filesystem would.

    `Path.replace` is the call that actually moves the staged bytes onto the
    target, so making it raise is the narrowest stand-in for a full or
    read-only filesystem: the plan is well-formed, the target has not moved,
    and only the filesystem says no.

    Both the text and the JSON test install this, so the two differ only in the
    output format under test rather than in the failure they provoke.

    Raises
    ------
    PermissionError
        Always. The message is the one a read-only mount would give.
    """
    message = "Read-only file system"
    raise PermissionError(message)


class TestWriteFailuresAreReported:
    """A filesystem that refuses a write is reported, not raised.

    `write_source` documents `OSError` in its own `Raises` section, so the
    executor has always had a failure mode it did not handle: catching only
    `SourceChangedOnDiskError` let a full or read-only filesystem escape as a
    traceback, abandoning every file after it and reporting nothing about the
    files already written or why the run stopped.
    """

    def test_a_permission_failure_is_reported_and_exits_two(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rejected write becomes a refusal and an operational-error status.

        `Path.replace` is what actually moves the staged bytes onto the target,
        so making it raise is the narrowest way to stand in for a read-only
        filesystem: the plan is well-formed, the target has not moved, and only
        the filesystem says no.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        monkeypatch.setattr(pathlib.Path, "replace", refuse_replace)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert_with_context(
            exit_code == 2,
            "expected a filesystem refusal to exit two",
        )
        assert_with_context(
            target.read_text(encoding="utf-8") == "Paragraph text.\n",
            "expected a refused write to leave the source unchanged",
        )
        assert_with_context(
            "fix-error/write-failed" in stream.getvalue(),
            f"expected the rendered refusal in {stream.getvalue()!r}",
        )
        assert_with_context(
            f"fix-error/write-failed: {target.name}:" in stream.getvalue(),
            "expected the rendered refusal to name the path it left alone",
        )
        assert_with_context(
            "Read-only file system" in stream.getvalue(),
            "expected the rendered refusal to carry the filesystem's reason",
        )
        assert_with_context(
            "0 files fixed, 0 fixes applied, 1 files skipped (conflict), "
            "1 fixes rejected" in stream.getvalue(),
            "expected the run summary to reach the report, not only the log",
        )


class TestStalePlanRefusals:
    """A target that moved under its plan is refused, and says so.

    The write path's staleness guarantee is only useful if the refusal reaches
    the user. `write_source` raises the same typed error for a target edited
    before staging and during it, so both windows are reported by the same
    channel -- and the channel holding every refusal, including the ones
    discovered after every plan was read, is the execution outcome rather than
    the aggregated diagnostics.

    A stale plan exits `1`, not `2`. The documented contract separates the two
    failure families: a conflict or a refusal is a *planning decision*, so the
    file is untouched and the diagnostic that prompted the plan still stands,
    while a write failure is an environment fault that exits `2`. A target that
    moved under its plan is the first family -- the run decided not to write,
    and the finding it was planning against is still true of the bytes on disk.
    """

    def test_a_stale_plan_is_reported_and_exits_one(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A target edited between planning and writing is refused and reported.

        The edit is applied by intercepting `read_bytes`: the check reads the
        source before it plans, and the writer does not consult that path again,
        so the target changes at a deterministic point after the plan exists and
        before any write begins. `write_source` then finds bytes that do not
        match the ones it planned from and refuses.

        The assertion that matters is the pair: the refusal is rendered with its
        identifier and path, *and* the human edit is still there. A refusal that
        reported success while overwriting, or that overwrote while reporting
        nothing, would satisfy neither half.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        original_read_bytes = pathlib.Path.read_bytes

        def edit_on_first_read(path: pathlib.Path) -> bytes:
            """Apply one edit after the source has been read for planning."""
            payload = original_read_bytes(path)
            if path.name == target.name:
                target.write_text("Human edit.\n", encoding="utf-8")
            return payload

        monkeypatch.setattr(pathlib.Path, "read_bytes", edit_on_first_read)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert_with_context(
            target.read_text(encoding="utf-8") == "Human edit.\n",
            "expected the human edit to survive the refusal",
        )
        assert_with_context(
            "fix-error/changed-on-disk" in stream.getvalue(),
            f"expected the staleness refusal in {stream.getvalue()!r}",
        )
        assert_with_context(
            f"fix-error/changed-on-disk: {target.name}: the file changed on disk"
            in stream.getvalue(),
            "expected the rendered refusal to name the path it left alone",
        )
        assert exit_code == 1, (
            "expected a stale plan to exit one: the run decided not to write, "
            "and the diagnostic it was planning against still stands"
        )

    def test_a_stale_plan_is_refused_in_json_output_too(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Carry the same refusal in the JSON document a tool reads.

        The JSON renderer puts refusals in their own top-level key, so a run
        that reported them only in text would hand a machine consumer a
        document with an empty ``fix_errors`` list and an exit status of one --
        a failed mutation with no stated cause. `--diff` is excluded because the
        patch owns standard output there and reports refusals on standard error.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        original_read_bytes = pathlib.Path.read_bytes

        def edit_on_first_read(path: pathlib.Path) -> bytes:
            """Apply one edit after the source has been read for planning."""
            payload = original_read_bytes(path)
            if path.name == target.name:
                target.write_text("Human edit.\n", encoding="utf-8")
            return payload

        monkeypatch.setattr(pathlib.Path, "read_bytes", edit_on_first_read)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True, output_format="json"),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert_with_context(
            '"identifier": "fix-error/changed-on-disk"' in stream.getvalue(),
            f"expected the JSON refusal in {stream.getvalue()!r}",
        )
        assert_with_context(
            f'"path": "{target.name}"' in stream.getvalue(),
            "expected the JSON refusal to name the untouched path",
        )
        assert exit_code == 1, "expected a stale plan to exit one in JSON too"


class TestWriteFailuresInJsonOutput:
    """The refused-write cause survives serialization too.

    The text test above proves the filesystem's reason reaches a human. This
    one proves the same refusal reaches a machine: the JSON document carries
    the identifier, the path, and the status, so a tool that reads only the
    document can tell a refused write from a clean run.
    """

    def test_a_permission_failure_is_reported_in_json_too(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Serialize a refused write as a JSON refusal, not a silent exit two.

        The exit status is asserted alongside the document because the two are
        separate promises: a run could report the refusal and still exit `0`,
        which would tell a script the mutation succeeded. Both halves are
        needed for the report to be actionable.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        monkeypatch.setattr(pathlib.Path, "replace", refuse_replace)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True, output_format="json"),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert_with_context(
            '"identifier": "fix-error/write-failed"' in stream.getvalue(),
            f"expected the JSON refusal in {stream.getvalue()!r}",
        )
        assert_with_context(
            f'"path": "{target.name}"' in stream.getvalue(),
            "expected the JSON refusal to name the path it left alone",
        )
        assert_with_context(
            "Read-only file system" in stream.getvalue(),
            "expected the serialized refusal to carry the filesystem's reason",
        )
        assert exit_code == 2, "expected a refused write to exit two in JSON too"
