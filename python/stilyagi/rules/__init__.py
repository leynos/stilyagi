"""Rule package boundary for Stilyagi.

This namespace is the Python-side home for bundled rules and future external
rule-pack loading. The mixed-package skeleton keeps the rule engine in Python,
so later slices can discover built-in and third-party rule modules without
teaching the Rust extractor about Python packaging concerns.

The package exports the `builtin` subpackage for Stilyagi's default rules.
Third-party rule packs are discovered at runtime through the
`stilyagi.rules` entry-point group defined by
`stilyagi.plugins.RULE_ENTRY_POINT_GROUP`, for example:

```toml
[project.entry-points."stilyagi.rules"]
acme_rules = "acme_stilyagi.rules"
```

Use this package for imports that need the rule namespace itself:

```python
from stilyagi.rules import builtin
```

Third-party rule packs will eventually register their rule modules through the
`stilyagi.rules` entry-point group described in :mod:`stilyagi.plugins`.
Runtime code should treat this package as the namespace entry for rule loading,
not as a place to import third-party implementations directly.
"""

from . import builtin

__all__ = ["builtin"]
