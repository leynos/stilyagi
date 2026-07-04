"""Docstring edge-case fixture for Python extraction."""


def multiline_docstring() -> None:
    """Line one.

    Line two.
    """


def raw_docstring() -> None:
    r"""Keep \n and \t escapes verbatim."""


def quote_and_escape_docstring() -> None:
    """Mention "double quotes", 'single quotes', and a \\ backslash."""  # noqa: D301 - preserve backslash test data.


def empty_docstring() -> None:
    """"""  # noqa: D419 - preserve empty docstring test data.


def whitespace_docstring() -> None:
    # Preserve multiple spaces as docstring content test data.
    """   """  # fmt: skip  # noqa: D419 - preserve blank content.


def f_string_first_statement(value: str) -> None:  # noqa: D103 - f-string must not be a docstring.
    f"""Not a v1 docstring: {value}."""  # noqa: B021 - negative parser fixture.


def concatenated_first_statement() -> None:
    # Preserve adjacent string grammar as negative docstring test data.
    "Not " "a v1 docstring."  # fmt: skip  # noqa: ISC001 - preserve grammar shape.


def byte_string_first_statement() -> None:  # noqa: D103 - byte string must not be a docstring.
    b"""Not a v1 docstring: bytes."""  # noqa: B018 - negative parser fixture.
