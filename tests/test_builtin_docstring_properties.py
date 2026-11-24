"""Property tests for the documentation-summary rules.

The finite matrix in ``test_builtin_docstring_rules`` pins named examples. These
properties generate owner names, summary text, and rule-selection orders to
check that the rules' promises hold beyond the examples: a finding appears
exactly when the documented predicate holds, its anchor addresses the expected
source character even across multibyte text and synthetic Rust line breaks, and
the reported order does not depend on how the configuration was assembled.

Every property builds a real Python or Rust fixture and runs it through the
real extractor and registry. A property that never produced a finding would
prove nothing, so each one asserts a matching witness exists.
"""

import copy
import itertools
import keyword
import string

import hypothesis as hyp
import hypothesis.strategies as st
import pytest
from stilyagi import diagnostics, model
from stilyagi.engine import rule_view
from stilyagi.model.source import SourceSpan
from stilyagi.rules.registry import run_rules

from tests.support.assertions import assert_with_context
from tests.support.rule_fixtures import LintSetup, marked_span

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

ALL_ENABLED: dict[str, dict[str, object]] = {
    "DOC001": {"enabled": True},
    "DOC002": {"enabled": True},
    "DOC003": {"enabled": True},
}

_NAME_ALPHABET = string.ascii_letters + "_"
_IDENTIFIERS = st.text(alphabet=_NAME_ALPHABET, min_size=1, max_size=10).filter(
    str.isidentifier
)
_PLAIN_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " ",
    min_size=0,
    max_size=20,
)
_TERMINALS = st.sampled_from([".", "!", "?", ",", ";", "9", "…"])
_WORDS = st.text(alphabet=string.ascii_letters, min_size=1, max_size=10)
_NON_ASCII_LETTERS = st.sampled_from(["é", "ß", "λ", "字", "🧭"])


def _python(source: str) -> list[diagnostics.Diagnostic]:
    """Run the enabled documentation rules over one Python source."""
    return LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.py").run(
        source, model.Syntax.PYTHON_DOCSTRING
    )


def _rust(source: str) -> list[diagnostics.Diagnostic]:
    """Run the enabled documentation rules over one Rust source."""
    return LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.rs").run(
        source, model.Syntax.RUST_DOC_COMMENT
    )


def _codes(result: list[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order."""
    return tuple(diagnostic.code for diagnostic in result)


@hyp.given(name=_IDENTIFIERS, other=_IDENTIFIERS)
def test_doc003_reports_only_the_matching_owner(name: str, other: str) -> None:
    """DOC003 fires exactly when the summary repeats the owner's own name."""
    hyp.assume(not keyword.iskeyword(name))
    hyp.assume(not keyword.iskeyword(other))
    hyp.assume(other != name)
    source = f'class {name}:\n    """{name}."""\n\nclass {other}:\n    """{name}."""\n'

    result = _python(source)

    assert_with_context(
        _codes(result) == ("DOC003",),
        f"expected one DOC003 for {name!r}, got {_codes(result)}",
    )
    assert_with_context(
        marked_span(source.encode(), result) == name[0].encode(),
        "expected the anchor to be the documented name's first character",
    )
    assert_with_context(
        result[0].line == 2,
        f"expected the finding on the matching class, got line {result[0].line}",
    )


@hyp.given(body=_PLAIN_TEXT, terminal=_TERMINALS)
def test_doc002_presence_follows_terminal_punctuation(
    body: str,
    terminal: str,
) -> None:
    """DOC002 reports exactly when the trimmed summary lacks ``.``, ``!``, ``?``."""
    source = f'def read():\n    """{body}{terminal}"""\n'

    codes = _codes(_python(source))

    if terminal in ".!?":
        assert_with_context(
            "DOC002" not in codes, f"expected {terminal!r} to be accepted, got {codes}"
        )
    else:
        assert_with_context(
            codes.count("DOC002") == 1,
            f"expected one DOC002 for terminal {terminal!r}, got {codes}",
        )


@hyp.given(character=_NON_ASCII_LETTERS)
def test_doc001_anchor_covers_one_complete_character(character: str) -> None:
    """A multibyte anchor is reported as its whole UTF-8 sequence."""
    source = f'def read():\n    """Read records.\n    {character} continues.\n    """\n'

    result = _python(source)

    assert _codes(result) == ("DOC001",), f"expected one DOC001, got {_codes(result)}"
    assert_with_context(
        marked_span(source.encode(), result) == character.encode(),
        "expected the anchor to decode to the first character of line two",
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert_with_context(
        span.byte_end - span.byte_start == len(character.encode()),
        "expected the span to cover exactly one character's bytes",
    )


@hyp.given(first=_WORDS, last=_NON_ASCII_LETTERS)
def test_doc002_rust_anchor_survives_synthetic_line_breaks(
    first: str,
    last: str,
) -> None:
    """A wrapped Rust summary anchors through the second line's segment."""
    hyp.assume(last.isalpha())
    source = f"/// Read {first}\n/// and {last}\npub fn read() {{}}\n"

    result = _rust(source)

    assert _codes(result) == ("DOC002",), f"expected one DOC002, got {_codes(result)}"
    assert_with_context(
        marked_span(source.encode(), result) == last.encode(),
        "expected the anchor to be the final character of the second line",
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert span.byte_start >= 4, "expected the anchor to sit after the comment marker"
    assert_with_context(
        result[0].line == 2,
        f"expected the finding on the second comment line, got {result[0].line}",
    )


@pytest.mark.parametrize(
    "order",
    list(itertools.permutations(("DOC001", "DOC002", "DOC003"))),
    ids="-".join,
)
def test_every_configuration_order_reports_the_same_findings(
    order: tuple[str, ...],
) -> None:
    """Each of the six table orders yields the same ordered findings."""
    rules: dict[str, dict[str, object]] = {code: {"enabled": True} for code in order}
    setup = LintSetup(select=("DOC",), rules=rules, reported_path="doc.py")
    source = 'class Widget:\n    """Widget"""\n'

    result = setup.run(source, model.Syntax.PYTHON_DOCSTRING)

    assert_with_context(
        _codes(result) == ("DOC002", "DOC003"),
        f"expected inventory order for table order {order}, got {_codes(result)}",
    )


@hyp.given(prefix=_PLAIN_TEXT, character=_NON_ASCII_LETTERS)
def test_anchor_matches_an_independently_computed_source_position(
    prefix: str,
    character: str,
) -> None:
    """Both span boundaries equal the position computed from the fixture text."""
    detail = f"{prefix}{character} continues."
    docstring = f'"""Module summary.\n{detail}"""\n'
    # Independently computed: the anchor is the first non-whitespace character
    # of the second content line, found by scanning the fixture itself.
    second_line = docstring.splitlines()[1]
    anchor_char = second_line.lstrip()[0]
    line_start = len(docstring[: docstring.index(second_line)].encode("utf-8"))
    leading = len(second_line) - len(second_line.lstrip())
    expected_start = line_start + len(second_line[:leading].encode("utf-8"))
    expected_end = expected_start + len(anchor_char.encode("utf-8"))

    result = LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.py").run(
        docstring, model.Syntax.PYTHON_DOCSTRING
    )

    assert_with_context(
        _codes(result) == ("DOC001",),
        f"expected one DOC001 finding, got {_codes(result)}",
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert_with_context(
        (span.byte_start, span.byte_end) == (expected_start, expected_end),
        f"expected the span {expected_start}..{expected_end}, got "
        f"{span.byte_start}..{span.byte_end}",
    )
    assert_with_context(
        docstring.encode()[span.byte_start : span.byte_end].decode() == anchor_char,
        "expected the span to address the independently located character",
    )


def test_a_run_leaves_the_extracted_request_unchanged() -> None:
    """Rules are queries: the extracted document and source bytes do not change."""
    source = (
        'class Widget:\n    """Widget"""\n\n'
        'def read():\n    """Read records.\n    More detail.\n    """\n'
    )
    setup = LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.py")
    request = setup.request_for(source, model.Syntax.PYTHON_DOCSTRING)
    before_ir = copy.deepcopy(dict(request.document.ir or {}))
    before_segments = copy.deepcopy([
        (region.region_id, tuple(region.scope), tuple(s.text for s in region.segments))
        for region in rule_view.project(
            request.document, source_bytes=request.source_bytes
        ).regions
    ])
    before_source = request.source_bytes

    run_rules(request)

    assert_with_context(
        dict(request.document.ir or {}) == before_ir,
        "expected the extracted IR to be unchanged by a run",
    )
    after_segments = [
        (region.region_id, tuple(region.scope), tuple(s.text for s in region.segments))
        for region in rule_view.project(
            request.document, source_bytes=request.source_bytes
        ).regions
    ]
    assert_with_context(
        after_segments == before_segments,
        "expected the projected regions to be unchanged by a run",
    )
    assert_with_context(
        request.source_bytes == before_source,
        "expected the source bytes to be unchanged by a run",
    )


@pytest.mark.parametrize(
    "select",
    list(itertools.permutations(("DOC001", "DOC002", "DOC003"))),
    ids="-".join,
)
def test_rule_selection_order_does_not_change_the_findings(
    select: tuple[str, ...],
) -> None:
    """Selection order, not only table order, leaves the report unchanged."""
    setup = LintSetup(select=select, rules=ALL_ENABLED, reported_path="doc.py")
    source = 'class Widget:\n    """Widget"""\n'

    result = setup.run(source, model.Syntax.PYTHON_DOCSTRING)

    assert_with_context(
        [(item.code, item.line, item.column, item.span) for item in result]
        == [
            ("DOC002", 2, 13, SourceSpan(26, 27)),
            ("DOC003", 2, 8, SourceSpan(21, 22)),
        ],
        f"expected identical ordered findings for selection {select}, "
        f"got {[(i.code, i.line, i.column) for i in result]}",
    )


@hyp.given(first=_WORDS, character=_NON_ASCII_LETTERS)
def test_rust_anchor_matches_an_independently_computed_source_position(
    first: str,
    character: str,
) -> None:
    """A merged Rust summary's span equals the fixture-computed position."""
    hyp.assume(character.isalpha())
    source = f"/// Read {first}\n/// and {character}\npub fn read() {{}}\n"
    # Independently computed: the anchor is the final character of the second
    # comment line, located by scanning the fixture text itself.
    lines = source.splitlines()
    anchor_char = lines[1][-1]
    expected_start = len(lines[0].encode("utf-8")) + 1
    expected_start += len(lines[1][:-1].encode("utf-8"))
    expected_end = expected_start + len(anchor_char.encode("utf-8"))

    result = LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.rs").run(
        source, model.Syntax.RUST_DOC_COMMENT
    )

    assert_with_context(
        _codes(result) == ("DOC002",),
        f"expected one DOC002 finding, got {_codes(result)}",
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert_with_context(
        (span.byte_start, span.byte_end) == (expected_start, expected_end),
        f"expected the span {expected_start}..{expected_end}, got "
        f"{span.byte_start}..{span.byte_end}",
    )
    assert_with_context(
        source.encode()[span.byte_start : span.byte_end].decode() == anchor_char,
        "expected the span to address the final character of the second line",
    )
