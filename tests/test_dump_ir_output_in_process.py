"""In-process framing and spool contracts for `dump-ir` output.

`cli_dump_ir_output` writes the canonical documents `dump-ir` harvested into
one JSON document or array without reserializing them. Driving the command
through a subprocess leaves these framing branches unmeasured, so they are
exercised directly here: a spool that ends early, an array that needs its
separating commas, and the closing newline canonical output must have.
"""

import io

import pytest
from stilyagi import cli_dump_ir_output


def test_dump_ir_output_writes_text_streams_through_the_decoder() -> None:
    """Decode a spooled document for a text-only output stream."""
    output_spool = io.BytesIO("héllo".encode())
    output = io.StringIO()

    cli_dump_ir_output._copy_spool_to_output(output_spool, output)

    assert output.getvalue() == "héllo", (
        "a text stream must receive the decoded document text"
    )


def test_dump_ir_output_reports_a_truncated_document_spool() -> None:
    """Refuse a document spool shorter than its recorded length."""
    document_spool = io.BytesIO(b"")
    output_spool = io.BytesIO()

    with pytest.raises(cli_dump_ir_output.DumpIrSpoolError, match="ended unexpectedly"):
        cli_dump_ir_output._write_json_framing(output_spool, document_spool, (4,))


def test_dump_ir_output_reports_a_truncated_array_document() -> None:
    """Refuse a truncated document while framing a multi-document array."""
    document_spool = io.BytesIO(b"{}")
    output_spool = io.BytesIO()

    with pytest.raises(cli_dump_ir_output.DumpIrSpoolError, match="ended unexpectedly"):
        cli_dump_ir_output._write_json_framing(output_spool, document_spool, (2, 4))


def test_dump_ir_output_separates_array_documents_with_commas() -> None:
    """Frame several spooled documents without reserializing their IR."""
    document_spool = io.BytesIO(b'{"a":1}{"b":2}')
    output_spool = io.BytesIO()

    cli_dump_ir_output._write_json_framing(output_spool, document_spool, (7, 7))

    assert output_spool.getvalue() == b'[{"a":1},{"b":2}]\n', (
        "array framing must preserve each canonical document verbatim"
    )


def test_dump_ir_output_adds_the_missing_canonical_newline() -> None:
    """Guarantee canonical output ends with exactly one newline."""
    assert cli_dump_ir_output._canonical_bytes("{}") == b"{}\n", (
        "missing framing newlines must be added"
    )
    assert cli_dump_ir_output._canonical_bytes("{}\n") == b"{}\n", (
        "an existing framing newline must not be doubled"
    )


def test_dump_ir_output_flushes_a_binary_stream() -> None:
    """Flush binary output after the final chunk."""

    class RecordingOutput(io.BytesIO):
        """Record whether the command flushed the completed output."""

        flushed = False

        def flush(self) -> None:
            """Record the flush request made by the command."""
            self.flushed = True
            super().flush()

    output = RecordingOutput()

    cli_dump_ir_output._copy_spool_to_output(io.BytesIO(b"{}"), output)

    assert output.getvalue() == b"{}", "binary output must receive the spool bytes"
    assert output.flushed, "binary output must be flushed after the final chunk"
