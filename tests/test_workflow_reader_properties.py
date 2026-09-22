"""Properties of the step, secret and configuration readings.

The tables in `test_workflow_reader_units` and
`test_workflow_secret_sweep` fix the finite spellings GitHub accepts.
These readings are different in kind: their subject is an arbitrary
number of jobs and steps in arbitrary order, with malformed fragments
among them and the secret at any of several scopes, and no table of
handwritten documents covers that space.

The documents are workflow-shaped rather than free-form. A free-form
nested mapping almost never puts a value where these readers look, so a
property over one stays green with the readers' shape guards deleted;
here every generated value lands at a level the reader visits: the jobs
block, a job, its steps list, one step, and a step's `env` and `with`.
"""

import json
import typing as typ

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.support.markdownlint_config import without_comments
from tests.support.workflow_secrets import FORBIDDEN_VARIABLE, secret_sites
from tests.support.workflows import triggers, workflow_steps

#: How a step, job or workflow reads the secret by reference.
READ: typ.Final[str] = f"${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}"

#: Values that mention the secret without reading it. Each must be
#: ignored, so a reading that matched the bare name would report them.
DECOYS: typ.Final[tuple[str, ...]] = (
    f"echo {FORBIDDEN_VARIABLE} is only set on main",
    "${{ secrets.OTHER_TOKEN }}",
    "",
)

#: Short text for the places whose content is not the subject. A small
#: alphabet, because a full-Unicode `st.text` builds Hypothesis's
#: character tables on first use, slowly enough to trip the health check
#: on whichever property draws first.
SHORT_TEXT: typ.Final[st.SearchStrategy[str]] = st.text(alphabet="ab: -", max_size=5)

#: Anything that is not a mapping, for the places a mapping belongs.
MALFORMED: typ.Final[st.SearchStrategy[object]] = st.one_of(
    st.none(), SHORT_TEXT, st.integers(), st.lists(SHORT_TEXT, max_size=2)
)

#: An `env` mapping and the site suffix it produces: the variable as
#: the key, a reference under another key, or neither.
ENV_FORMS: typ.Final[tuple[tuple[dict[str, str], str | None], ...]] = (
    ({FORBIDDEN_VARIABLE: "x"}, "env"),
    ({"TOKEN": READ}, "env value TOKEN"),
    ({"OTHER": DECOYS[0]}, None),
)

#: A drawn step entry: the step and its site suffixes, or `None` where a
#: malformed entry stands in the steps list.
type Entry = tuple[dict[str, object], list[str]] | None

#: A drawn workflow: the document, its secret sites, and its mapping
#: steps in declaration order.
type Drawn = tuple[dict[str | bool, object], list[str], list[dict[str, object]]]


@st.composite
def _step(draw: st.DrawFn) -> tuple[dict[str, object], list[str]]:
    """Draw one mapping step and the site suffixes it holds, in reading order."""
    env, env_site = draw(st.sampled_from(ENV_FORMS))
    reads_inputs, reads_run = draw(st.booleans()), draw(st.booleans())
    decoy = draw(st.sampled_from(DECOYS))
    step: dict[str, object] = {
        "env": env,
        "with": {"access-token": READ} if reads_inputs else {"note": decoy},
        "run": f"curl -H {READ}" if reads_run else decoy,
    }
    found = [env_site] if env_site else []
    found += [
        scope
        for scope, reads in (("inputs", reads_inputs), ("run", reads_run))
        if reads
    ]
    return step, found


@st.composite
def _job(draw: st.DrawFn) -> tuple[object, list[str], list[Entry]]:
    """Draw one job, the job-level site suffixes it holds, and its step entries."""
    if draw(st.integers(min_value=0, max_value=5)) == 0:
        return draw(MALFORMED), [], []
    entries: list[Entry] = draw(st.lists(st.one_of(_step(), st.none()), max_size=4))
    env, env_site = draw(st.sampled_from(ENV_FORMS))
    inherits = draw(st.booleans())
    job: dict[str, object] = {
        "env": env,
        "steps": [entry[0] if entry else draw(MALFORMED) for entry in entries],
    }
    if inherits:
        job["secrets"] = "inherit"
    job_sites = [
        site for site in (env_site, "secrets: inherit" if inherits else None) if site
    ]
    return job, job_sites, entries


@st.composite
def _workflow(draw: st.DrawFn) -> Drawn:
    """Draw a workflow, the secret sites it holds and its mapping steps in order."""
    jobs = draw(st.lists(_job(), max_size=4))
    env, env_site = draw(st.sampled_from(ENV_FORMS))
    document: dict[str | bool, object] = {
        "on": {"pull_request": ""},
        "env": env,
        "jobs": {f"job{index}": job for index, (job, _, _) in enumerate(jobs)},
    }
    sites = [f"ci.yml: workflow {env_site}"] if env_site else []
    steps: list[dict[str, object]] = []
    for index, (_, job_sites, entries) in enumerate(jobs):
        sites += [f"ci.yml: job job{index} {site}" for site in job_sites]
        for position, entry in enumerate(entries):
            if entry is not None:
                steps.append(entry[0])
                where = f"ci.yml: job job{index} step {position + 1}"
                sites += [f"{where} {site}" for site in entry[1]]
    return document, sites, steps


@settings(max_examples=200)
@given(_workflow())
def test_the_step_reading_keeps_every_mapping_step_in_order(drawn: Drawn) -> None:
    """Every mapping step, in declaration order, and nothing else.

    A malformed job or step contributes nothing and raises nothing,
    wherever it sits among well-formed ones.
    """
    document, _, steps = drawn
    assert workflow_steps(document) == steps, (
        "the mapping steps, in order, and no other"
    )


@settings(max_examples=200)
@given(_workflow())
def test_the_secret_reading_reports_every_and_only_the_reads(drawn: Drawn) -> None:
    """Every scope that reads the secret is reported, in order, and no decoy.

    The expected sites are recorded as the document is drawn: workflow,
    job and step `env` in both the key and the value form, `secrets:
    inherit`, step inputs and step scripts, across any number of jobs and
    steps in any order, with prose naming the variable and other
    secrets' references alongside.
    """
    document, sites, _ = drawn
    assert secret_sites("ci.yml", document) == sites, "every read, in order, no decoy"


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
