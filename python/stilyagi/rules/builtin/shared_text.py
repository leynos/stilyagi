"""Constants shared by the builtin rule catalogue's authored records.

Every rule's prose cites the same governing documents and states the same
limitation about static metadata. Stating either twice would let the copies
drift, so both live here and each rule module imports them.
"""

__all__ = ["REFERENCES", "STATIC_ENABLEMENT_LIMIT"]

#: Governing documents every shipped rule cites.
REFERENCES: tuple[str, ...] = (
    "docs/rfcs/rfc-0002-stilyagi-python-rule-api.md",
    "docs/stilyagi-design.md#72-python-rule-api",
    "docs/adrs/adr-0012-adopt-the-source-backed-builtin-rule-contract.md",
)

#: Shared limitation: static metadata cannot describe per-file enablement.
STATIC_ENABLEMENT_LIMIT: str = (
    "Configuration, per-file ignores, and suppression directives can stop a "
    "finding; static metadata does not describe effective enablement for a "
    "particular file."
)
