"""Where the CodeScene token may appear in the publisher.

The upload is `upload-codescene-coverage`, a composite action. A
composite action's nested steps inherit the calling step's environment,
so a token bound in the upload step's `env`, or the job's, or the
workflow's, reaches every step inside the action. The publisher
therefore keeps the token out of every `env`. A check step publishes
only whether the token exists, the upload's condition reads that
output, and the upload takes the token directly as an input.

The positive half matters as much as the prohibition. Deleting the
token entirely satisfies "no `env` holds it" while the upload's guard
goes false and publishing silently stops, so the token must be named
exactly twice: in the check step's command and in the upload's input.

Each assertion is proved by putting the forbidden element back.

Run via `make test`.
"""

import typing as typ

from tests.support.codescene_coverage import CODESCENE_ACTION, publishers
from tests.support.workflows import workflow_jobs, workflow_steps

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from tests.support.workflows import WorkflowDocument

#: The check step's one command. GitHub evaluates the expression before
#: the shell starts, so the command writes a literal `true` or `false`
#: and the token enters no process.
CHECK_COMMAND: typ.Final[str] = (
    'echo "available=${{ secrets.CS_ACCESS_TOKEN != \'\' }}" >> "$GITHUB_OUTPUT"'
)
CHECK_STEP_ID: typ.Final[str] = "codescene_token"
AVAILABLE_CONJUNCT: typ.Final[str] = (
    f"steps.{CHECK_STEP_ID}.outputs.available == 'true'"
)
UPLOAD_CREDENTIAL_INPUT: typ.Final[str] = "${{ secrets.CS_ACCESS_TOKEN }}"
#: Expression contexts are case-insensitive, so scans compare case-folded.
CREDENTIAL_NAME: typ.Final[str] = "cs_access_token"


def _publisher(documents: dict[str, WorkflowDocument]) -> WorkflowDocument:
    """Return the one publisher workflow."""
    ((_, document),) = publishers(documents).items()
    return document


def _is_upload(step: dict[str, object]) -> bool:
    """Report whether a step calls the CodeScene uploader."""
    return CODESCENE_ACTION in str(step.get("uses", ""))


def _upload_job_steps(document: WorkflowDocument) -> list[dict[str, object]]:
    """Return the steps of the one publisher job that uploads."""
    jobs = [
        [step for step in job.get("steps") or [] if isinstance(step, dict)]
        for job in workflow_jobs(document).values()
    ]
    uploading = [steps for steps in jobs if any(map(_is_upload, steps))]
    assert len(uploading) == 1, f"one job must upload, found {len(uploading)}"
    return uploading[0]


def _strings(value: object) -> cabc.Iterator[str]:
    """Yield every string in a parsed YAML value, mapping keys included.

    Keys count because an `env` entry names the token as a key as
    readily as a value does.

    Yields
    ------
    str
        Each string in document order, a mapping's key before its value.

    Examples
    --------
    >>> list(_strings({"env": {"TOKEN": "x"}, "steps": ["a", 1]}))
    ['env', 'TOKEN', 'x', 'steps', 'a']
    """
    match value:
        case str():
            yield value
        case dict():
            for key, item in value.items():
                yield from _strings(key)
                yield from _strings(item)
        case list():
            for item in value:
                yield from _strings(item)
        case _:
            return


def _names_credential(value: object) -> bool:
    """Report whether any string in `value` names the token."""
    return any(CREDENTIAL_NAME in text.casefold() for text in _strings(value))


def test_the_check_step_publishes_availability_and_nothing_else(
    documents: dict[str, WorkflowDocument],
) -> None:
    """One unconditional command writes a boolean, with no env.

    A condition on the check would leave its output unset whenever the
    condition was false, so the upload would skip forever, and an `env`
    on it would put the token back into an environment. The check must
    also precede the upload that reads it, in the same job: a step's
    outputs are visible only to later steps of its own job, so a check
    in another job leaves the upload skipping forever.
    """
    steps = _upload_job_steps(_publisher(documents))
    checks = [step for step in steps if step.get("id") == CHECK_STEP_ID]
    assert len(checks) == 1, f"the upload's job must carry one {CHECK_STEP_ID!r} step"
    (check,) = checks
    assert str(check.get("run", "")).strip() == CHECK_COMMAND, check.get("run")
    assert "if" not in check, "the check must run unconditionally"
    assert "env" not in check, "the check must declare no env"
    uploads = [step for step in steps if _is_upload(step)]
    assert len(uploads) == 1, f"one upload step expected, found {len(uploads)}"
    assert steps.index(check) < steps.index(uploads[0]), (
        "the check must run before the upload that reads its output"
    )


def test_the_upload_reads_the_check_and_takes_the_token_directly(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The upload is guarded on the check's output and given the secret."""
    ((upload,),) = (
        (step,)
        for step in workflow_steps(_publisher(documents))
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    conjuncts = [part.strip() for part in str(upload.get("if", "")).split("&&")]
    assert AVAILABLE_CONJUNCT in conjuncts, upload.get("if")
    inputs = upload.get("with") or {}
    assert isinstance(inputs, dict), inputs
    assert inputs.get("access-token") == UPLOAD_CREDENTIAL_INPUT, inputs.get(
        "access-token"
    )


def test_no_environment_on_the_publisher_holds_the_token(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The workflow, job and step environments never name the token."""
    document = _publisher(documents)
    environments = [
        document.get("env"),
        *(job.get("env") for job in workflow_jobs(document).values()),
        *(step.get("env") for step in workflow_steps(document)),
    ]
    holders = [env for env in environments if _names_credential(env)]
    assert not holders, (
        f"no env on the publisher may name the token, found {holders!r}; a "
        f"composite action's nested steps inherit the calling step's env"
    )


def test_the_token_appears_exactly_where_it_is_used(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The token is named in the check's command and the upload's input."""
    mentions = sorted(
        text.strip()
        for text in _strings(_publisher(documents))
        if CREDENTIAL_NAME in text.casefold()
    )
    assert mentions == sorted([CHECK_COMMAND, UPLOAD_CREDENTIAL_INPUT]), mentions
