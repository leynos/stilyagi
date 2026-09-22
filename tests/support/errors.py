"""The exception base every test-support helper raises through."""


class SupportError(Exception):
    """Base for every fault raised by a test-support helper.

    Carries a structured `reader` rather than leaving a caller to parse
    a message. The helpers in this package are readings over the
    repository, and the useful question when one fails is always which
    reading it was: "the reader is broken" and "the repository does not
    comply" are different answers and must not look alike.

    Attributes
    ----------
    reader : str
        The reading that failed, named as the caller would name it.
    """

    def __init__(self, message: str, *, reader: str) -> None:
        """Record the message and the reading it came from.

        Parameters
        ----------
        message : str
            What went wrong, for a person reading the failure.
        reader : str
            The reading that failed.
        """
        super().__init__(message)
        self.reader = reader
