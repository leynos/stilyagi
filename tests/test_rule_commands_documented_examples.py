"""Exercise the rule-discovery transcripts the user's guide publishes.

Each command line a reader copies out of the guide must be one the parser
accepts, and each published output line must be what the command actually
writes. The examples come from the guide through the shared loader, so editing
the prose changes the test's input rather than leaving a stale copy behind.
"""

import io
import shlex
import typing as typ

import pytest
from stilyagi import cli, rule_commands
from stilyagi.cli_args import build_parser
from stilyagi.cli_rule_args import RuleDetailOptions

if typ.TYPE_CHECKING:
    import pathlib

from tests.support.tested_examples import MarkedExample, load_tested_examples

_EXAMPLES = load_tested_examples()


def _example(name: str) -> MarkedExample:
    """Return one marked example, failing clearly when the guide lost it."""
    assert name in _EXAMPLES, f"expected the guide to mark {name}"
    return _EXAMPLES[name]


def test_every_rule_invocation_in_the_guide_parses() -> None:
    """Each `stilyagi rules …` line the guide shows is accepted by the parser."""
    example = _example("rules-invocations")
    assert example.language == "shell", "expected a shell transcript"

    parser = build_parser()
    for line in example.lines:
        arguments = shlex.split(line)[1:]
        parsed = parser.parse_args(arguments)
        assert parsed.command == "rules", f"expected `parse {line}` to select rules"


def test_every_rule_detail_invocation_in_the_guide_parses() -> None:
    """Each `stilyagi rule …` line the guide shows selects the detail command."""
    example = _example("rule-invocations")
    assert example.language == "shell", "expected a shell transcript"

    parser = build_parser()
    for line in example.lines:
        arguments = shlex.split(line)[1:]
        parsed = parser.parse_args(arguments)
        assert parsed.command == "rule", f"expected `parse {line}` to select rule"


def test_the_guide_s_rules_transcript_really_lists_the_inventory() -> None:
    """The plain `stilyagi rules` line the guide shows succeeds and lists the code."""
    example = _example("rules-invocations")
    parser = build_parser()
    plain = next(line for line in example.lines if line.strip() == "stilyagi rules")
    parsed = parser.parse_args(shlex.split(plain)[1:])

    assert parsed.command == "rules", "expected the plain invocation to select rules"


def test_the_guide_unknown_code_transcript_matches_the_command() -> None:
    """The published unknown-code transcript is the command's real behaviour."""
    example = _example("rule-unknown-code")
    assert example.lines[0] == "$ stilyagi rule MD", "expected the documented command"
    assert example.lines[1] == "stilyagi rule: unknown rule code: MD", (
        "expected the documented failure line"
    )
    assert example.lines[3] == "2", "expected the documented exit status"

    result, failure = io.StringIO(), io.StringIO()
    status = rule_commands.run_rule_detail(
        RuleDetailOptions("MD"), output=result, error=failure
    )

    assert status == int(example.lines[3]), "expected the documented exit status"
    assert not result.getvalue(), "expected nothing on standard output"
    assert failure.getvalue() == example.lines[1] + "\n", (
        "expected the documented failure line"
    )


#: Every discovery invocation the guide publishes, with its document status.
#: The two blocks list only invocations the guide presents as succeeding, so
#: each status is ``0``. The status is asserted rather than assumed because the
#: commands share the real dispatch path with `check`.
_DOCUMENTED_DISCOVERY_LINES = [
    pytest.param(line, 0, id=f"{name}:{number}")
    for name in ("rules-invocations", "rule-invocations")
    for number, line in enumerate(_example(name).lines)
]


@pytest.mark.parametrize(("line", "expected_status"), _DOCUMENTED_DISCOVERY_LINES)
def test_documented_invocations_succeed_with_their_stated_status(
    line: str,
    expected_status: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every documented invocation succeeds through the real dispatch path."""
    monkeypatch.setattr(
        cli,
        "run_check",
        _unexpected_check,
        raising=True,
    )

    status = cli.main(shlex.split(line)[1:])

    assert status == expected_status, f"expected `{line}` to exit {expected_status}"
    capsys.readouterr()


def _unexpected_check(*_args: object, **_kwargs: object) -> typ.NoReturn:
    """Fail the test when a discovery invocation falls through to `check`."""
    message = "rule discovery must not dispatch to check"
    raise AssertionError(message)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        pytest.param(
            "<!-- tested-example: a -->\n```text\nline\n",
            "no closing fence",
            id="unclosed-fence",
        ),
        pytest.param(
            "<!-- tested-example: a -->\n\nno fence here\n",
            "names no fenced block",
            id="marker-without-fence",
        ),
        pytest.param(
            "<!-- tested-example: a -->\n<!-- tested-example: a -->\n```text\nx\n```\n",
            "names no fenced block before marker",
            id="marker-before-marker",
        ),
        pytest.param(
            "<!-- tested-example: a -->\n```text\nx\n```\n"
            "<!-- tested-example: a -->\n```text\ny\n```\n",
            "duplicate tested-example marker",
            id="duplicate-marker",
        ),
        pytest.param("```text\nx\n```\n", "unmarked fence", id="unmarked-fence"),
    ],
)
def test_the_loader_rejects_a_malformed_document(
    body: str,
    match: str,
    tmp_path: pathlib.Path,
) -> None:
    """A malformed marker or fence fails rather than loading silently.

    Silent tolerance would let a renamed marker leave a test reading nothing
    while still passing, so each shape the style guide forbids is rejected.
    """
    path = tmp_path / "guide.md"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_tested_examples(path)


def test_a_language_tagged_fence_inside_a_block_stays_content(
    tmp_path: pathlib.Path,
) -> None:
    """Only a bare closing fence ends a block, so nested fences are content."""
    path = tmp_path / "guide.md"
    path.write_text(
        "<!-- tested-example: nested -->\n```markdown\n```python\nprint('x')\n```\n",
        encoding="utf-8",
    )

    examples = load_tested_examples(path)

    assert examples["nested"].lines == ("```python", "print('x')"), (
        "expected the inner language-tagged fence to stay in the block"
    )


def test_an_indented_marker_and_fence_are_dedented(tmp_path: pathlib.Path) -> None:
    """A block nested in a list item loads its content without the list indent."""
    path = tmp_path / "guide.md"
    path.write_text(
        "- an item:\n"
        "\n"
        "  <!-- tested-example: indented -->\n"
        "  ```python\n"
        "  value = 1\n"
        "  ```\n",
        encoding="utf-8",
    )

    examples = load_tested_examples(path)

    assert examples["indented"].lines == ("value = 1",), (
        "expected the list indentation to be removed from the block"
    )
