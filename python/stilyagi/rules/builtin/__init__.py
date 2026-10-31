"""Built-in rule package boundary for Stilyagi.

The starter pack declares three deterministic rules. ``MD`` structural rules
come first, then ``STY`` style rules, then opt-in ``TERM`` rules, which is the
documented code-prefix scheme.

Each rule runs once per document against only the regions its
:class:`~stilyagi.rules.base.RegionTarget` claims. Rules run in inventory order
so diagnostics are deterministic, and a rule still evaluates its full state
when its findings are later suppressed. The inventory and runner live in
:mod:`stilyagi.rules.builtin.pack`; this module re-exports them so callers keep
one stable import path.
"""

from .pack import (
    BuiltinRule,
    enabled_codes,
    inventory,
    registry_codes,
    run_selected,
)

__all__ = [
    "BuiltinRule",
    "enabled_codes",
    "inventory",
    "registry_codes",
    "run_selected",
]
