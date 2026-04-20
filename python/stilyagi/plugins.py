"""Plugin discovery constants for the mixed-package skeleton.

Stilyagi keeps rule and capability discovery on the Python side of the
architecture. External packages will eventually register plugins through
standard Python entry points, while the Rust layer remains focused on source
extraction and IR construction.

This module defines the entry-point group names the runtime uses when it asks
Python packaging metadata for installed plugins. In `pyproject.toml`, PEP 621
entry-point groups map a stable group name such as `stilyagi.rules` to one or
more import targets that a package wants to expose at runtime.

`RULE_ENTRY_POINT_GROUP` is the discovery group for rule-pack modules.
`CAPABILITY_ENTRY_POINT_GROUP` is the discovery group for capability-provider
modules. Future plugin packages should point their `pyproject.toml` entry-point
tables at these groups, for example:

```toml
[project.entry-points."stilyagi.rules"]
acme_markdown = "acme_stilyagi.rules"

[project.entry-points."stilyagi.capabilities"]
acme_nlp = "acme_stilyagi.capabilities"
```

Keeping the names here avoids hard-coded strings leaking across the package and
gives the developer guide one importable source of truth for plugin discovery.
See the Developer's Guide for the surrounding package-boundary rationale.
"""

RULE_ENTRY_POINT_GROUP: str = "stilyagi.rules"
CAPABILITY_ENTRY_POINT_GROUP: str = "stilyagi.capabilities"

__all__ = ["CAPABILITY_ENTRY_POINT_GROUP", "RULE_ENTRY_POINT_GROUP"]
