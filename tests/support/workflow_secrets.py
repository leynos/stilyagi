"""Where a workflow puts a secret in reach of a process.

Separated from `codescene_coverage` because the question is a general
one and the answer is the same whatever the secret is: a rule about any
of them needs this, not only CV-005's.

Structural rather than textual, and that distinction is the whole
point. A workflow that explains in prose why a secret is absent
mentions its name, and a sweep over the raw file reads the explanation
as the violation; the first version of this reading did exactly that
and failed on its own comment.

What matters is whether a process can read the secret, and there are
more routes than an `env` key. The name can be the key, so
`CS_ACCESS_TOKEN: ...` is one; but the *value* can carry it under any
key at all, so `ANYTHING: ${{ secrets.CS_ACCESS_TOKEN }}` is another
and the key says nothing. A reusable-workflow call forwards secrets
through `jobs.<id>.secrets`, either naming one or, with `inherit`,
handing over every secret the caller has without naming any.
"""

import re
import typing as typ

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

#: The name of the secret and the environment variable no pull-request
#: lane may put in reach. The name rather than any value: the
#: expression supplying it may be a secret, a repository variable or a
#: literal, and all three reach the process the same way.
FORBIDDEN_VARIABLE: typ.Final[str] = "CS_ACCESS_TOKEN"

#: An expression reading the secret, under any of the contexts GitHub
#: resolves one from. Matched on the reference rather than on the bare
#: name so that a literal string, or prose, is not mistaken for access:
#: what puts the secret in reach is `${{ secrets.NAME }}`, and a value
#: that merely equals the name is a different thing entirely.
_SECRET_REFERENCE: typ.Final[re.Pattern[str]] = re.compile(
    rf"\$\{{\{{\s*(?:secrets|env|vars)\.{re.escape(FORBIDDEN_VARIABLE)}\s*\}}\}}"
)


def _reaches(value: object) -> bool:
    """Return whether a value names the secret or reads it by reference."""
    text = str(value)
    return bool(_SECRET_REFERENCE.search(text))


def _mapping_sites(name: str, where: str, mapping: object) -> list[str]:
    """Return sites where an env mapping declares or forwards the secret."""
    if not isinstance(mapping, dict):
        return []
    sites: list[str] = []
    if FORBIDDEN_VARIABLE in mapping:
        sites.append(f"{name}: {where} env")
    sites += [
        f"{name}: {where} env value {key}"
        for key, value in mapping.items()
        if key != FORBIDDEN_VARIABLE and _reaches(value)
    ]
    return sites


def _secrets_sites(name: str, job_name: str, forwarded: object) -> list[str]:
    """Return sites where a reusable-workflow call forwards the secret.

    `secrets: inherit` is the sharp one. It names nothing, so a reading
    that looked for the variable would find no mention of it while the
    called workflow receives every secret the caller holds, this one
    among them.

    Parameters
    ----------
    name : str
        The workflow's file name, for the message.
    job_name : str
        The job declaring the call.
    forwarded : object
        The job's `secrets` value, as the document supplied it.

    Returns
    -------
    list of str
        One entry per forwarding site, empty when there is none.
    """
    match forwarded:
        case str() if forwarded.strip() == "inherit":
            return [f"{name}: job {job_name} secrets: inherit"]
        case dict():
            return [
                f"{name}: job {job_name} secrets {key}"
                for key, value in forwarded.items()
                if key == FORBIDDEN_VARIABLE or _reaches(value)
            ]
        case _:
            return []


def _step_sites(name: str, job_name: str, steps: object) -> list[str]:
    """Return every site one job's steps put the secret in reach."""
    if not isinstance(steps, list):
        return []
    sites: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        where = f"job {job_name} step {index + 1}"
        sites += _mapping_sites(name, where, step.get("env"))
        inputs = step.get("with")
        if isinstance(inputs, dict) and any(
            _reaches(value) for value in inputs.values()
        ):
            sites.append(f"{name}: {where} inputs")
        if _reaches(step.get("run", "")) or FORBIDDEN_VARIABLE in str(
            step.get("run", "")
        ):
            sites.append(f"{name}: {where} run")
    return sites


def secret_sites(name: str, document: WorkflowDocument) -> list[str]:
    """Return every place one workflow puts the secret in reach.

    Parameters
    ----------
    name : str
        The workflow's file name, for the message.
    document : WorkflowDocument
        The parsed workflow.

    Returns
    -------
    list of str
        One entry per site, naming where it is. Empty when nothing in
        the document can read the secret.
    """
    sites = _mapping_sites(name, "workflow", document.get("env"))
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return sites
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        sites += _mapping_sites(name, f"job {job_name}", job.get("env"))
        sites += _secrets_sites(name, str(job_name), job.get("secrets"))
        sites += _step_sites(name, str(job_name), job.get("steps"))
    return sites
