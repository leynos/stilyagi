"""Rule package boundary for Stilyagi.

This namespace is the Python-side home for bundled rules and future external
rule-pack loading. The mixed-package skeleton keeps the rule engine in Python,
so later slices can discover built-in and third-party rule modules without
teaching the Rust extractor about Python packaging concerns.

Use this package for imports that need the rule namespace itself:

```python
from stilyagi.rules import builtin
```

Third-party rule packs will eventually register their rule modules through the
`stilyagi.rules` entry-point group described in :mod:`stilyagi.plugins`.
"""

from . import builtin

__all__ = ["builtin"]
