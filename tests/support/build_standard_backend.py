"""Judge whether the Cranelift backend is adopted or its exception recorded.

The estate default selects the Cranelift codegen backend for the dev profile
where the full suite passes under it. A repository either carries the backend
(the `[profile.dev]` key, the `[unstable]` switch cargo requires for it, and the
toolchain component) or records an exception in its developer's guide, under a
heading that names Cranelift and the pinned channel. The exception goes stale
on every pin move, which is the point: a bump has to re-evaluate it.

The judgement is a pure function over parsed documents so a contract can drive
it over constructed configurations in both directions.
"""

import re
import typing as typ

BACKEND_COMPONENT: typ.Final = "rustc-codegen-cranelift-preview"
_HEADING: typ.Final = re.compile(r"^(#+)\s+(.*)$")
_EXCEPTION_MARKER: typ.Final = "not part of the standard"


def _tables(config: dict[str, object], name: str) -> dict[str, object]:
    """Return the `name` table of a parsed configuration, or an empty one."""
    table = config.get(name, {})
    return table if isinstance(table, dict) else {}


def backend_keys(config: dict[str, object]) -> list[str]:
    """Return every `codegen-backend` key a configuration declares.

    Returns
    -------
    list[str]
        `profile.<name>` for each profile selecting a backend, and `unstable`
        for the switch.
    """
    profiles = _tables(config, "profile")
    keys = [
        f"profile.{name}"
        for name, table in profiles.items()
        if isinstance(table, dict) and "codegen-backend" in table
    ]
    if "codegen-backend" in _tables(config, "unstable"):
        keys.append("unstable")
    return keys


def is_adopted(config: dict[str, object]) -> bool:
    """Return whether the dev profile selects Cranelift."""
    dev = _tables(config, "profile").get("dev", {})
    return isinstance(dev, dict) and dev.get("codegen-backend") == "cranelift"


def _heading_parts(line: str) -> tuple[int, str] | None:
    """Return a heading line's level and text, or None for a body line."""
    match = _HEADING.match(line)
    if match is None:
        return None
    return len(match.group(1)), match.group(2)


def _section_body(lines: list[str], start: int, level: int) -> list[str]:
    """Return the heading at `start` and every line under it."""
    body = [lines[start]]
    for later in lines[start + 1 :]:
        heading = _heading_parts(later)
        if heading is not None and heading[0] <= level:
            break
        body.append(later)
    return body


def cranelift_section(guide: str) -> str | None:
    """Return the guide section whose heading names Cranelift, if any.

    Returns
    -------
    str | None
        The heading and its body up to the next heading of the same or a
        shallower level, or None when no heading mentions Cranelift.
    """
    lines = guide.splitlines()
    for start, line in enumerate(lines):
        heading = _heading_parts(line)
        if heading is None or "cranelift" not in heading[1].lower():
            continue
        return "\n".join(_section_body(lines, start, heading[0]))
    return None


def backend_faults(
    config: dict[str, object], toolchain: dict[str, typ.Any], guide: str
) -> list[str]:
    """Return why neither adoption nor the exception is correctly recorded.

    Returns
    -------
    list[str]
        One entry per fault; empty when the repository is consistent.
    """
    section = cranelift_section(guide)
    if is_adopted(config):
        return _adoption_faults(config, toolchain, section)
    return _exception_faults(config, toolchain, section)


def _adoption_faults(
    config: dict[str, object], toolchain: dict[str, typ.Any], section: str | None
) -> list[str]:
    """Return what an adopted backend is missing or contradicts."""
    faults: list[str] = []
    if _tables(config, "unstable").get("codegen-backend") is not True:
        faults.append("the backend key needs [unstable] codegen-backend = true")
    if BACKEND_COMPONENT not in toolchain.get("components", ()):
        faults.append(f"rust-toolchain.toml lacks {BACKEND_COMPONENT}")
    if section is not None and _EXCEPTION_MARKER in section.splitlines()[0].lower():
        faults.append("the guide still records an exception for an adopted backend")
    return faults


def _exception_faults(
    config: dict[str, object], toolchain: dict[str, typ.Any], section: str | None
) -> list[str]:
    """Return what a recorded exception is missing or contradicts."""
    faults = [
        f"{key} selects a backend despite the exception" for key in backend_keys(config)
    ]
    if section is None:
        faults.append("no developer's guide heading names Cranelift")
    elif str(toolchain.get("channel")) not in section:
        faults.append("the exception does not name the pinned channel; it is stale")
    return faults
