"""The estate Markdown formatting baseline, as CI has to hold it.

Concordat rule `markdown-formatting-baseline`. The Makefile half landed
already; what is asserted here is the half that lives in CI, because it
is the half a local run cannot tell you about: Markdown is linted only
through `DavidAnson/markdownlint-cli2-action`, pinned to a full commit
SHA, over every Markdown file in the tree.

A `run:` step invoking the linter is the thing this rule exists to
exclude. It resolves the tool from a registry at run time, so the rules
applied to a pull request depend on when it ran, and the pin that is
supposed to make CI reproducible then says nothing about the linter
actually used.

Run via `make test`.
"""

import pathlib
import re
import typing as typ

import pytest

from tests.support.workflows import load_workflow, workflow_steps

REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"

#: The action CI lints Markdown through.
MARKDOWNLINT_ACTION: typ.Final[str] = "DavidAnson/markdownlint-cli2-action"

#: The `v24.2.0` annotated *tag object*, which this repository pinned
#: and several others still do. It is forty hex characters and it is
#: immutable, so a rule checking the shape of a pin accepts it, and it
#: is indistinguishable from a commit in a diff. PD-006 asks for the
#: commit, which for this tag is
#: `21c1be1b93ad9ed58fa840aacc3f279cde2a72ff`, read by dereferencing the
#: tag through the GitHub refs API rather than assembled.
#:
#: Named here as a value to *refuse* rather than a value to require.
#: Section 6f of the developers' guide forbids a contract from holding
#: a caller's current SHA, because Dependabot owns these bumps and the
#: test would then fail on every one. Refusing one known-bad value
#: survives a bump; it is also all this contract can do offline, since
#: nothing in the tree says whether a forty-character reference is a
#: commit or a tag.
MARKDOWNLINT_TAG_OBJECT: typ.Final[str] = "4580e1612f6407034edd6c0e4e316d725920867b"

#: A full-length commit pin, per section 6f: the shape is asserted, the
#: value is not.
PINNED_COMMIT: typ.Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

#: Every Markdown file, which is the scope the rule asks the action to
#: cover. The ignores live in `.markdownlint-cli2.jsonc` rather than in
#: the glob, so the workflow and `make markdownlint` exclude the same
#: paths.
REQUIRED_GLOBS: typ.Final[str] = "**/*.md"

#: The linter's command name, for the run-step sweep.
LINTER_COMMAND: typ.Final[str] = "markdownlint-cli2"


def _documents() -> dict[str, dict[str, object]]:
    """Return every workflow document, keyed by file name."""
    found = {
        path.name: load_workflow(path.read_text(encoding="utf-8"))
        for pattern in ("*.yml", "*.yaml")
        for path in sorted(WORKFLOWS.glob(pattern))
    }
    assert found, (
        f"no workflow documents were read from {WORKFLOWS}; the assertions "
        f"below are all satisfied by a reading that finds nothing, so this "
        f"is the reader failing rather than the repository complying"
    )
    return found


def _linting_steps() -> list[tuple[str, dict[str, object]]]:
    """Return every step invoking the Markdown linter action."""
    return [
        (name, step)
        for name, document in _documents().items()
        for step in workflow_steps(document)
        if MARKDOWNLINT_ACTION in str(step.get("uses", ""))
    ]


def test_ci_lints_markdown_through_the_action() -> None:
    """Exactly one step, and it is the action.

    None would mean CI does not lint Markdown at all, which every
    assertion below is satisfied by, so the count is pinned rather than
    the shape alone.
    """
    steps = _linting_steps()
    assert len(steps) == 1, (
        f"expected exactly one step using {MARKDOWNLINT_ACTION}; found "
        f"{[name for name, _ in steps]}"
    )


def test_the_action_is_pinned_to_a_commit_not_a_tag_object() -> None:
    """A tag object's SHA is immutable and is still not a commit.

    This repository pinned `4580e161`, the `v24.2.0` annotated tag
    object, rather than the commit it points at. Both are forty hex
    characters, so the shape assertion below passes on either and the
    two are indistinguishable in a diff.

    What is asserted is the shape plus a refusal of that one known tag
    object. The current commit is deliberately not named, because
    section 6f of the developers' guide forbids holding a caller's SHA
    in a contract: Dependabot owns the bump and the test would fail on
    every one.

    That leaves a gap this docstring should state rather than hide. A
    future release's tag object would pass, because nothing in the tree
    distinguishes a tag from a commit and the check is offline. The
    remedy when Dependabot next bumps this action is to dereference the
    tag through the refs API before accepting the pin, the same way this
    one was found.
    """
    ((name, step),) = _linting_steps()
    reference = str(step.get("uses", ""))
    prefix = f"{MARKDOWNLINT_ACTION}@"
    assert reference.startswith(prefix), (
        f"{name} must call {MARKDOWNLINT_ACTION} by path; it calls {reference!r}"
    )
    pinned = reference[len(prefix) :].split(" ", 1)[0]
    assert PINNED_COMMIT.match(pinned), (
        f"{name} pins {pinned!r}, which is not a full forty-character "
        f"commit; a branch or a tag name moves under the workflow"
    )
    assert pinned != MARKDOWNLINT_TAG_OBJECT, (
        f"{name} pins the v24.2.0 annotated tag object rather than the "
        f"commit it points at; PD-006 asks for the commit, which for this "
        f"tag is 21c1be1b93ad9ed58fa840aacc3f279cde2a72ff"
    )


def test_the_action_lints_every_markdown_file() -> None:
    """The glob is the scope; the ignores are the config's job.

    A narrower glob in the workflow would silently exempt whole
    directories from CI while `make markdownlint` still covered them,
    and the two would disagree about whether the tree is clean.
    """
    ((name, step),) = _linting_steps()
    inputs = step.get("with") or {}
    assert isinstance(inputs, dict), (
        f"the step's `with:` block is not a mapping: {inputs!r}"
    )
    assert inputs.get("globs") == REQUIRED_GLOBS, (
        f"{name} must lint {REQUIRED_GLOBS!r}; it lints {inputs.get('globs')!r}"
    )


def test_no_workflow_runs_the_linter_directly() -> None:
    """A run step resolves the tool at run time, which is the whole point.

    The pin above is what makes CI's Markdown verdict reproducible. A
    `run:` step invoking `markdownlint-cli2` gets whichever version the
    registry serves that day, so the pin stays green while saying
    nothing about the linter that actually ran.
    """
    offenders = sorted(
        f"{name}: {str(step.get('run', '')).strip()[:60]}"
        for name, document in _documents().items()
        for step in workflow_steps(document)
        if LINTER_COMMAND in str(step.get("run", ""))
    )
    assert not offenders, (
        f"these steps invoke {LINTER_COMMAND} from a run body rather than "
        f"through the pinned action: {offenders}"
    )


@pytest.mark.parametrize(
    "entry",
    [
        "**/.venv/**",
        ".vtcode/**",
        "**/node_modules/**",
        "**/target/**",
        ".terraform/**",
        ".uv-cache/**",
        "memories/**",
        "CRUSH.md",
    ],
)
def test_the_config_carries_every_canonical_ignore(entry: str) -> None:
    """The canonical entries are present; extras beside them are allowed.

    The rule asks for the canonical `.markdownlint-cli2.jsonc` copied
    verbatim and permits further rules and ignores to sit beside the
    baseline entries. Asserted as presence rather than as equality for
    that reason: this repository adds `.node_modules/**` and
    `**/.act-cache/**`, which the rule allows, and an equality check
    would refuse them while an absent baseline entry is the thing that
    actually matters.
    """
    config = (REPOSITORY_ROOT / ".markdownlint-cli2.jsonc").read_text(encoding="utf-8")
    assert f'"{entry}"' in config, (
        f".markdownlint-cli2.jsonc drops the canonical ignore {entry!r}; the "
        f"baseline entries are the part that must be copied verbatim"
    )
