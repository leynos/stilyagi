"""Properties of the step and trigger readings and the comment stripper.

The tables in `test_workflow_reader_units` fix the finite spellings GitHub
accepts. These readings are different in kind: their subject is an arbitrary
number of jobs and steps in arbitrary order, with malformed fragments among
them, and no table of handwritten documents covers that space.

The documents are workflow-shaped rather than free-form. A free-form nested
mapping almost never puts a value where these readers look, so a property over
one stays green with the readers' shape guards deleted; here every generated
value lands at a level the reader visits: the jobs block, a job and its steps
list.
"""

import json
import typing as typ

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.support.markdownlint_config import without_comments
from tests.support.workflows import triggers, workflow_steps

#: Short text for the places whose content is not the subject. A small
#: alphabet, because a full-Unicode `st.text` builds Hypothesis's
#: character tables on first use, slowly enough to trip the health check
#: on whichever property draws first.
SHORT_TEXT: typ.Final[st.SearchStrategy[str]] = st.text(alphabet="ab: -", max_size=5)

#: Anything that is not a mapping, for the places a mapping belongs.
MALFORMED: typ.Final[st.SearchStrategy[object]] = st.one_of(
    st.none(), SHORT_TEXT, st.integers(), st.lists(SHORT_TEXT, max_size=2)
)

#: A drawn workflow: the document and its mapping steps in declaration order.
type Drawn = tuple[dict[str | bool, object], list[dict[str, object]]]


@st.composite
def _step(draw: st.DrawFn) -> dict[str, object]:
    """Draw one mapping step."""
    return {
        "name": draw(SHORT_TEXT),
        "run": draw(SHORT_TEXT),
        "with": draw(st.dictionaries(SHORT_TEXT, SHORT_TEXT, max_size=2)),
    }


@st.composite
def _job(draw: st.DrawFn) -> tuple[object, list[dict[str, object]]]:
    """Draw one job (or a malformed stand-in) and its mapping steps in order."""
    if draw(st.integers(min_value=0, max_value=5)) == 0:
        return draw(MALFORMED), []
    entries = draw(st.lists(st.one_of(_step(), MALFORMED), max_size=4))
    mapping_steps = [entry for entry in entries if isinstance(entry, dict)]
    return {"steps": entries}, mapping_steps


@st.composite
def _workflow(draw: st.DrawFn) -> Drawn:
    """Draw a workflow and its mapping steps in order."""
    jobs = draw(st.lists(_job(), max_size=4))
    document: dict[str | bool, object] = {
        "on": {"pull_request": ""},
        "jobs": {f"job{index}": job for index, (job, _) in enumerate(jobs)},
    }
    return document, [step for _, steps in jobs for step in steps]


@settings(max_examples=200)
@given(_workflow())
def test_the_step_reading_keeps_every_mapping_step_in_order(drawn: Drawn) -> None:
    """Every mapping step, in declaration order, and nothing else.

    A malformed job or step contributes nothing and raises nothing,
    wherever it sits among well-formed ones.
    """
    document, steps = drawn
    assert workflow_steps(document) == steps, (
        "the mapping steps, in order, and no other"
    )


@given(
    st.lists(
        st.sampled_from(("pull_request", "push", "workflow_dispatch")),
        min_size=1,
        unique=True,
    )
)
def test_the_trigger_reading_is_the_same_under_either_key(names: list[str]) -> None:
    """`on` keyed as the string or as the boolean `True` reads the same.

    A resolving loader keys an unquoted `on:` under `True`; a reader that
    looked under one key only would find no triggers for every workflow
    a loader of the other kind produced.
    """
    declared = dict.fromkeys(names, "")
    assert (
        triggers({"on": declared}) == triggers({True: declared}) == frozenset(names)
    ), f"{names} must read the same under the string and the boolean key"


#: JSON strings whose content is the subject: path separators, comment
#: openers, escaped quotes and backslashes are the characters a naive
#: stripper mistakes for comments or string ends.
JSON_TEXT: typ.Final[st.SearchStrategy[str]] = st.text(
    alphabet='ab/*"\\ \n', max_size=8
)


@given(
    st.dictionaries(st.sampled_from(("a", "b", "ignores")), JSON_TEXT, max_size=3),
    st.sampled_from(("// note\n", "/* note */", "/* // */", "")),
)
def test_comment_stripping_preserves_every_string(
    document: dict[str, str], comment: str
) -> None:
    """Comments outside strings go; everything inside a string stays.

    The comment is placed between every token, and the strings carry the
    characters that look like comment openers or string ends, so a
    stripper that lost track of whether it was inside a string would
    change a value or fail to parse.
    """
    text = json.dumps(document, indent=1).replace("\n", f"\n{comment}")
    assert json.loads(without_comments(f"{comment}{text}")) == document, (
        f"stripping {comment!r} changed a value in {text!r}"
    )
