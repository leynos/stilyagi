"""Contract coverage for the handler that makes structured log fields visible.

Every record this command emits carries its decision in the ``extra`` mapping
rather than in its message. The stdlib's default formatter renders the message
alone and drops ``extra`` entirely, so without this handler a per-file decision
reaches the user as the bare sentence `fix plan decided` -- no file identity,
none of the counters that are the reason the record exists.

Two things have to hold for that to be true, and they fail independently:
the handler must render the fields a record actually carries, and the field
list must name the keys production actually stamps. The second is the quieter
failure, because a key missing from the list is written, formatted away, and
never noticed -- the log simply lacks a value nobody knows to look for.
"""

import ast
import io
import logging
import pathlib
import typing as typ

from stilyagi import cli_log

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_PRODUCTION_ROOT = pathlib.Path(__file__).resolve().parents[1] / "python" / "stilyagi"


def _extra_arguments(tree: ast.Module) -> cabc.Iterator[ast.expr]:
    """Yield the argument of every ``extra=`` keyword in one parsed module.

    Knowing the AST shape is this function's whole job, so the two filters --
    a call, then a keyword named ``extra`` -- live here and nowhere else. That
    is what lets the scan below read as a walk over modules rather than a walk
    over syntax, and it is why the nesting does not have to be repeated at the
    call site.

    Returns
    -------
    cabc.Iterator[ast.expr]
        The value expression of each ``extra=`` keyword, in tree order.
    """
    return (
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "extra"
    )


def _string_keys(value: ast.expr) -> cabc.Iterator[str]:
    """Yield the literal string keys of one keyword argument's dict literal.

    Yields
    ------
    str
        A string constant used as a key. Anything else yields nothing rather
        than a guess: a computed key, or an argument that is not a dict literal
        at all, is skipped so the scan cannot report a field that is not there.
    """
    if not isinstance(value, ast.Dict):
        return
    for key in value.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            yield key.value


def _stamped_field_names() -> set[str]:
    """Return every key production passes to a logger through ``extra=``.

    The set is read from the source rather than restated here, because a
    restated list is a copy that can agree with itself while disagreeing with
    the tree. Every ``extra`` in this command is a dict literal, so the keys are
    all decidable statically.

    Returns
    -------
    set[str]
        The literal string keys of every ``extra`` dict literal under
        ``python/stilyagi``.
    """
    names: set[str] = set()
    for path in sorted(_PRODUCTION_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for argument in _extra_arguments(tree):
            names.update(_string_keys(argument))
    return names


def test_structured_fields_is_sorted_and_unique() -> None:
    """Keep the rendered field order stable and free of repeats.

    The handler joins the fields in list order, so the order is part of the
    rendered line. A record's fields are appended in this sequence regardless of
    the order the caller wrote them, which is what makes two runs comparable in
    a diff -- but only while the list stays sorted. A duplicate would also
    render the same value twice, which reads as two distinct fields.
    """
    fields = list(cli_log.STRUCTURED_FIELDS)

    assert_with_context(
        fields == sorted(fields), "expected the rendered field order to be sorted"
    )
    assert_with_context(
        len(fields) == len(set(fields)), "expected no field to be listed twice"
    )


def test_structured_fields_names_every_field_production_stamps() -> None:
    """Fail when production logs a field the handler would silently drop.

    This is the drift the module's own docstring warns about: a new ``extra``
    key that never reaches the list is written and never shown. Nothing else
    catches it -- the record still carries the attribute, so a `caplog` consumer
    reads it and every existing assertion passes, while the human-facing line
    omits it. The failure is a missing value, not a wrong one.
    """
    stamped = _stamped_field_names()
    missing = sorted(stamped - set(cli_log.STRUCTURED_FIELDS))

    assert_with_context(
        not missing,
        f"expected every stamped log field to be rendered, unlisted: {missing}",
    )
    assert_with_context(
        stamped, "expected the scan to find the command's structured log records"
    )


def _render(record: logging.LogRecord) -> str:
    """Return the line the production handler writes for one record.

    The record goes through the handler rather than through its formatter,
    because that is the only path that runs the filter and the filter is what
    appends the fields. Calling `format` directly would render the message
    alone and pass any assertion about fields only by accident.

    Returns
    -------
    str
        What the handler wrote to its stream, including the trailing newline.
    """
    handler = cli_log.log_handler()
    stream = io.StringIO()
    handler.setStream(stream)
    handler.handle(record)
    return stream.getvalue()


def _record(message: str) -> logging.LogRecord:
    """Build one bare INFO record for the handler to render."""
    return logging.LogRecord(
        name="stilyagi.example",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_handler_appends_every_structured_field_to_the_message() -> None:
    """Render a record's ``extra`` values into the line the user reads."""
    record = _record("fix plan decided")
    record.path = "notes.md"
    record.patch_byte_count = 42

    assert_with_context(
        _render(record) == "INFO stilyagi.example: fix plan decided "
        "(patch_byte_count=42, path='notes.md')\n",
        "expected the fields in list order, after the message",
    )


def test_handler_leaves_a_record_without_fields_alone() -> None:
    """Add no empty parenthesis to a record that carries no structured field.

    Most records in this command are plain sentences. Appending an empty
    `()` to each of them would be noise on every line of a verbose run, which is
    the cost the fixed list exists to avoid paying for the records that need it.
    """
    assert_with_context(
        _render(_record("check complete")) == "INFO stilyagi.example: check complete\n",
        "expected a record with no fields to render as its message alone",
    )


def test_handler_keeps_record_attributes_readable_after_formatting() -> None:
    """Format presentation without consuming the record a consumer reads.

    The handler rewrites ``msg``. A `caplog` consumer reads the attributes, not
    the message, so the rewrite must not disturb them: two consumers reading the
    same record for different purposes is the whole reason the value is in
    ``extra`` rather than interpolated into the sentence in the first place.
    """
    record = logging.LogRecord(
        name="stilyagi.example",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="fix execution finished",
        args=(),
        exc_info=None,
    )
    record.files_written = 2

    cli_log.log_handler().filters[0](record)

    assert_with_context(
        record.files_written == 2, "expected the attribute to survive formatting"
    )
    assert_with_context(
        record.args == (),
        "expected arguments to be cleared once they are interpolated, so a "
        "second formatting pass cannot re-apply them",
    )
