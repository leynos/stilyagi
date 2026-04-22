"""Built-in rule package boundary for Stilyagi.

The repository's own bundled rules will live under this namespace once the
real rule-engine slices land. It exists now so the mixed-package skeleton has
an explicit reserved home for built-ins instead of scattering that contract
across design notes.

External packages should not import private implementation modules from here.
They should register their own rule namespaces through the
`stilyagi.rules` entry-point group in `pyproject.toml`, where they will be
discovered and loaded by the runtime, for example:

```toml
[project.entry-points."stilyagi.rules"]
team_rules = "team_stilyagi.rules"
```

That keeps built-in rules, third-party rules, and discovery configuration
separate even though they all participate in the same Python-side rule engine.
Use this module only as the namespace marker for rule implementations shipped
with Stilyagi itself.
"""
