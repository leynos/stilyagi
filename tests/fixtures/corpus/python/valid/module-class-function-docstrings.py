"""Module docstring for the shared Stilyagi corpus."""


# stilyagi: ignore-next terminology
class FixtureExample:
    """Class docstring with prose for extraction tests."""

    @staticmethod
    def method() -> str:
        """Return a documented value from a method docstring."""
        return "documented"


# stilyagi: disable terminology
def fixture_function() -> None:
    """Use a function docstring for later Python extraction slices."""


# stilyagi: enable terminology
# stilyagi: ignore-file
# stilyagi: disable
