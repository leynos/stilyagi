"""spaCy-provider placeholders for Stilyagi."""

import dataclasses as dc


class InvalidSpacyModelError(ValueError):
    """Raised when the spaCy model identifier is blank."""


@dc.dataclass(frozen=True, slots=True)
class SpacyProviderConfig:
    """Placeholder configuration for the future spaCy provider.

    Parameters
    ----------
    model:
        spaCy model identifier for later NLP-backed slices.
    """

    model: str = "en_core_web_sm"

    def __post_init__(self) -> None:
        """Reject unusable empty spaCy model identifiers."""
        if not self.model.strip():
            message = f"Invalid spaCy model: {self.model!r}. It must not be blank."
            raise InvalidSpacyModelError(message) from None
