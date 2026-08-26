"""Docstring edge-case fixture for Python extraction."""


def multiline_docstring() -> None:
    """Line one.

    Line two.
    """


def raw_docstring() -> None:
    r"""Keep \n and \t escapes verbatim."""


def quote_and_escape_docstring() -> None:
    """Mention "double quotes", 'single quotes', and a \\ backslash."""  # ruff: ignore[escape-sequence-in-docstring] - preserve backslash test data.


def empty_docstring() -> None:
    """"""  # ruff: ignore[empty-docstring] - preserve empty docstring test data.


def whitespace_docstring() -> None:
    # Preserve multiple spaces as docstring content test data.
    """   """  # fmt: skip  # ruff: ignore[empty-docstring] - preserve blank content.


def f_string_first_statement(value: str) -> None:  # ruff: ignore[undocumented-public-function] - f-string must not be a docstring.
    f"""Not a v1 docstring: {value}."""  # ruff: ignore[f-string-docstring] - negative parser fixture.


def concatenated_first_statement() -> None:
    # Preserve adjacent string grammar as negative docstring test data.
    "Not " "a v1 docstring."  # fmt: skip  # ruff: ignore[single-line-implicit-string-concatenation] - preserve grammar shape.


def byte_string_first_statement() -> None:  # ruff: ignore[undocumented-public-function] - byte string must not be a docstring.
    b"""Not a v1 docstring: bytes."""  # ruff: ignore[useless-expression] - negative parser fixture.
