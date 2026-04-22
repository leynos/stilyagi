"""Natural language processing boundary for Stilyagi."""

from .base import NlpProvider
from .spacy_provider import SpacyProviderConfig

__all__ = ["NlpProvider", "SpacyProviderConfig"]
