"""The secret sweep, driven on documents this repository does not have.

Separated from ``test_workflow_reader_units`` so neither module
outgrows the 400-line limit the lint gate enforces, and because the
subject is its own: every route by which a workflow can hand a secret
to a process, and every shape that looks like one and is not.

The narrow half matters as much as the broad one. The first version of
this reading matched the raw file text and failed on the comment
explaining why a step had been removed, which would have left the next
person deleting the explanation to make the contract pass.

Run via `make test`.
"""

import typing as typ

import pytest

from tests.support.workflow_secrets import FORBIDDEN_VARIABLE, secret_sites
from tests.support.workflows import load_workflow

#: A minimal workflow body, so each case below varies one thing.
JOBS: typ.Final[str] = "jobs:\n  a:\n    steps: []\n"


@pytest.mark.parametrize(
    ("body", "where"),
    [
        pytest.param(
            f"env:\n  {FORBIDDEN_VARIABLE}: x\n{JOBS}", "workflow env", id="workflow"
        ),
        pytest.param(
            f"env:\n  OTHER: ${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}\n{JOBS}",
            "workflow env value OTHER",
            id="aliased-value",
        ),
        pytest.param(
            f"jobs:\n  a:\n    env:\n      {FORBIDDEN_VARIABLE}: x\n    steps: []\n",
            "job a env",
            id="job",
        ),
        pytest.param(
            "jobs:\n  a:\n    steps:\n      - env:\n"
            f"          {FORBIDDEN_VARIABLE}: x\n",
            "job a step 1 env",
            id="step",
        ),
        pytest.param(
            "jobs:\n  a:\n    steps:\n      - with:\n"
            f"          token: ${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}\n",
            "job a step 1 inputs",
            id="inputs",
        ),
        pytest.param(
            "jobs:\n  a:\n    steps:\n"
            f"      - run: echo ${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}\n",
            "job a step 1 run",
            id="run",
        ),
        pytest.param(
            "jobs:\n  a:\n    secrets:\n"
            f"      {FORBIDDEN_VARIABLE}: ${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}\n",
            f"job a secrets {FORBIDDEN_VARIABLE}",
            id="forwarded-secret",
        ),
        pytest.param(
            "jobs:\n  a:\n    secrets: inherit\n",
            "job a secrets: inherit",
            id="inherited-secrets",
        ),
    ],
)
def test_the_secret_sweep_finds_every_route(body: str, where: str) -> None:
    """Every way a workflow hands the secret to a process.

    The aliased value is the one a key-only reading misses: the variable
    can be called anything at all and still carry
    `${{ secrets.CS_ACCESS_TOKEN }}`.

    `secrets: inherit` is sharper still. It names nothing, so a reading
    looking for the variable finds no mention of it while the called
    workflow receives every secret the caller holds, this one included.
    """
    document = load_workflow(f"on:\n  pull_request:\n{body}")
    assert secret_sites("x.yml", document) == [f"x.yml: {where}"], (
        f"the sweep must find the secret at {where} in {body!r}"
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            (
                "jobs:\n  a:\n    steps:\n"
                f"      - run: echo hi  # no {FORBIDDEN_VARIABLE}\n"
            ),
            id="a-comment",
        ),
        pytest.param(
            "jobs:\n  a:\n    env:\n      OTHER: ${{ secrets.SOMETHING_ELSE }}\n"
            "    steps: []\n",
            id="another-secret",
        ),
        pytest.param(
            f"jobs:\n  a:\n    env:\n      OTHER: '{FORBIDDEN_VARIABLE}'\n"
            "    steps: []\n",
            id="a-literal-naming-it",
        ),
        pytest.param("jobs:\n  a:\n    secrets:\n      OTHER: x\n", id="other-secret"),
        pytest.param(
            f"jobs:\n  a:\n    steps:\n      - run: echo ${FORBIDDEN_VARIABLE}\n",
            id="a-bare-shell-variable",
        ),
    ],
)
def test_the_secret_sweep_is_narrow(body: str) -> None:
    """Assert the sweep above refuses only what it should.

    Its first version matched the raw file text and failed on the
    comment explaining why a step had been removed, which would have
    left the next person deleting the explanation to make the contract
    pass. A comment is not a secret, another secret is not this one, and
    a literal equal to the name reads nothing.

    A bare `$CS_ACCESS_TOKEN` in a `run` body is here for a subtler
    reason. It reads an environment variable rather than the secret, so
    it puts nothing in reach on its own: if something set that variable,
    the `env` sweeps above have already reported it, and if nothing did
    it expands to empty. Reporting it here would double-count the one
    case and invent the other.
    """
    document = load_workflow(f"on:\n  pull_request:\n{body}")
    assert secret_sites("x.yml", document) == [], (
        f"nothing here puts the secret in reach: {body!r}"
    )
