"""Nested declaration fixture for Python docstring extraction."""

import pathlib


def outer_function() -> None:
    """Document an outer function."""

    def inner_function() -> None:
        """Document a function nested inside another function."""

    class LocalClass:
        """Document a class nested inside a function."""

        def method(self) -> None:
            """Document a method on a function-local class."""


class DecoratedExample:
    """Document a class containing decorated methods."""

    @classmethod
    def from_value(cls) -> "DecoratedExample":  # ruff: ignore[quoted-annotation] - forward reference to the enclosing class.
        """Document a class method."""
        return cls()

    @staticmethod
    @property
    def doubly_decorated() -> str:
        """Document a doubly decorated method."""
        return "value"


async def async_function() -> None:
    """Document a module-level async function."""


def statement_nested() -> None:
    """Document a function containing statement-nested definitions."""
    if True:

        def inside_if() -> None:
            """Document a function nested inside an if statement."""

    for _value in (1,):

        def inside_for() -> None:
            """Document a function nested inside a for statement."""

    with pathlib.Path(__file__).open(encoding="utf-8") as _handle:

        def inside_with() -> None:
            """Document a function nested inside a with statement."""
