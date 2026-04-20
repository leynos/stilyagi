"""Plugin discovery constants for the mixed-package skeleton.

Stilyagi keeps rule and capability discovery on the Python side of the
architecture. External packages will eventually register plugins through
standard Python entry points, while the Rust layer remains focused on source
extraction and IR construction.

The constants in this module are the stable names that plugin authors and the
runtime will share. Future plugin packages should point their `pyproject.toml`
entry-point tables at these groups, for example:

```toml
[project.entry-points."stilyagi.rules"]
acme_markdown = "acme_stilyagi.rules"

[project.entry-points."stilyagi.capabilities"]
acme_nlp = "acme_stilyagi.capabilities"
```

Keeping the names here avoids hard-coded strings leaking across the package and
gives the developer guide one importable source of truth for plugin discovery.
"""

RULE_ENTRY_POINT_GROUP = "stilyagi.rules"
CAPABILITY_ENTRY_POINT_GROUP = "stilyagi.capabilities"

__all__ = ["CAPABILITY_ENTRY_POINT_GROUP", "RULE_ENTRY_POINT_GROUP"]
