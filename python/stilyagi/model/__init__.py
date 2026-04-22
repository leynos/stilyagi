"""Document-model package boundary for Stilyagi."""

from .document import Document, Syntax
from .region import Region
from .sentence import Sentence
from .token import Token

__all__ = ["Document", "Region", "Sentence", "Syntax", "Token"]
