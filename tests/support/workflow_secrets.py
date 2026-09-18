"""Where a workflow puts an environment variable in reach.

Separated from `codescene_coverage` because the question is a general
one and the answer is the same whatever the variable is: a rule about
any secret needs it, not only CV-005's.

Structural rather than textual, and that distinction is the whole point.
A workflow that explains in prose why a variable is absent mentions its
name, and a sweep over the raw file reads the explanation as the
violation; the first version of this reading did exactly that and failed
on its own comment. What matters is whether a process can read the
variable, which means the `env` mappings at workflow, job and step
level, the inputs handed to an action, and the body of a `run` step.
"""

import typing as typ

#: The name of the environment variable no pull-request lane may put in
#: reach. The name rather than any value: the expression supplying it
#: may be a secret, a repository variable or a literal, and all three
#: reach the process the same way.
FORBIDDEN_VARIABLE: typ.Final[str] = "CS_ACCESS_TOKEN"


def _environment_sites(name: str, where: str, mapping: object) -> list[str]:
    """Return a site entry when an env mapping declares the variable."""
    if isinstance(mapping, dict) and FORBIDDEN_VARIABLE in mapping:
        return [f"{name}: {where} env"]
    return []


def _step_sites(name: str, job_name: str, steps: object) -> list[str]:
    """Return every site one job's steps put the variable in reach."""
    if not isinstance(steps, list):
        return []
    sites: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        where = f"job {job_name} step {index + 1}"
        sites += _environment_sites(name, where, step.get("env"))
        inputs = step.get("with")
        if isinstance(inputs, dict) and any(
            FORBIDDEN_VARIABLE in str(value) for value in inputs.values()
        ):
            sites.append(f"{name}: {where} inputs")
        if FORBIDDEN_VARIABLE in str(step.get("run", "")):
            sites.append(f"{name}: {where} run")
    return sites


def token_sites(name: str, document: dict[str, object]) -> list[str]:
    """Return every place one workflow puts the access token in reach.

    Structural rather than textual, and the distinction is the whole
    point of the helper. Both workflows explain in prose why the token
    is where it is, and a rule matching the raw file reads those
    comments as violations; the first version of this contract did
    exactly that and failed on its own explanation. What matters is
    whether a process can read the variable, which means the `env`
    mappings at workflow, job and step level, the inputs handed to an
    action, and the body of a `run` step.

    Parameters
    ----------
    name : str
        The workflow's file name, for the message.
    document : dict
        The parsed workflow.

    Returns
    -------
    list of str
        One entry per site, naming where it is.
    """
    sites = _environment_sites(name, "workflow", document.get("env"))
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return sites
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        sites += _environment_sites(name, f"job {job_name}", job.get("env"))
        sites += _step_sites(name, str(job_name), job.get("steps"))
    return sites
