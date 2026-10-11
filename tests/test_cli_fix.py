"""Unit coverage for `cli_fix.emit_fixed_document`.

`emit_fixed_document` is called directly here rather than through the command,
because it is a different boundary: the command decides whether a mutating run
took place at all, while this function decides only what a stream input's fixed
document looks like on the way out. The command-level coverage for a piped
input lives in `tests/test_check_mutation.py`.

Driving the function directly is also the only way to see two of the three
outcomes. A command-level test necessarily uses a document the rest of the
pipeline accepts, so it cannot present a plan whose every edit was refused, and
it cannot present one that merely looks like a stream input without being one.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_cli_fix.py
"""

import dataclasses as dc
import io
import typing as typ

from stilyagi import cli_fix

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import planned_file

if typ.TYPE_CHECKING:
    from stilyagi.engine.fix_pipeline import PlannedFile


class TestFixedDocumentEmission:
    """`emit_fixed_document` prints a piped file's replacement and nothing else."""

    def test_a_stream_input_prints_its_replacement_verbatim(self) -> None:
        """The piped document is emitted with no decoration added.

        `print` adds a newline nobody asked for, so `end=""` is load-bearing:
        the bytes a user piped in are theirs to capture, and a trailing newline
        here would be a byte the fixed document never contained. A source
        already ending in one would look correct either way, so this one does
        not end in one.

        `emit_fixed_document` is called directly rather than through the command
        because the command-level test drives a `#`-headed document, whose
        fixed text carries a newline and so cannot distinguish the two.
        """
        stream = io.StringIO()
        plan = _piped_plan("Paragraph text.", "Section text.")

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            stream.getvalue() == "Section text.",
            "expected the replacement bytes alone, with no appended newline",
        )

    def test_a_file_input_prints_nothing(self) -> None:
        """A file's replacement is written to disk, never to standard output.

        Emitting here as well would print the whole repaired document on a run
        that also wrote it, so the `from_stdin` guard is the whole behaviour
        under test. The plan is otherwise identical to the stream case above,
        which is what makes the flag the only thing the assertion can observe.
        """
        stream = io.StringIO()
        plan = dc.replace(
            _piped_plan("Paragraph text.", "Section text."), from_stdin=False
        )

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            not stream.getvalue(),
            "expected a file input's replacement to stay off standard output",
        )

    def test_a_conflicted_stream_input_prints_nothing(self) -> None:
        """A plan with no replacement has no document to emit.

        A stream input whose every edit was refused has `fixed_bytes` of
        ``None``, and there is nothing honest to print: emitting the unchanged
        source would tell a user their document was fixed. The guard folds "no
        replacement" and "not from a stream" into one decision, so this case and
        the file case are asserted separately -- they differ in why nothing is
        printed, and a regression could collapse either reason.
        """
        stream = io.StringIO()
        plan = _piped_plan("Paragraph text.", "Paragraph text.")

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            not stream.getvalue(),
            "expected a refused stream input to emit no document",
        )


def _piped_plan(source_text: str, fixed_text: str) -> PlannedFile:
    """Return a plan for one file whose bytes came from standard input.

    Returns
    -------
    PlannedFile
        The plan `planned_file` builds, flagged as a stream input. The flag is
        set here rather than passed through the shared fixture because that
        helper already sits at the project's four-argument ceiling.
    """
    return dc.replace(
        planned_file("notes.md", fixed_text, source_text=source_text),
        from_stdin=True,
    )
