"""The faults a nextest configuration can carry.

Separated from ``timeout_budgets`` so the duration grammar and the
budget arithmetic can both raise them without either importing the
other, and so neither module outgrows the 400-line limit ``AGENTS.md``
sets.
"""


class TimeoutBudgetError(ValueError):
    """Base for every fault these readings report.

    Callers catch this rather than matching message text, and the two
    fields carry what a caller would otherwise have to parse out of the
    message: which setting was at fault and what it held.

    Attributes
    ----------
    field : str
        The configuration key the fault is about.
    value : object
        What that key held, as the configuration gave it.
    """

    def __init__(self, message: str, *, field: str, value: object) -> None:
        """Record the message and the setting it is about.

        Parameters
        ----------
        message : str
            What went wrong, for a person reading the failure.
        field : str
            The configuration key the fault is about.
        value : object
            What that key held.
        """
        super().__init__(message)
        self.field = field
        self.value = value


class NextestConfigurationError(TimeoutBudgetError):
    """Raised when a nextest configuration cannot be read as written.

    A malformed duration or a `slow-timeout` without a period would
    otherwise be read as some plausible number, and the ordering above
    it would be checked against a value nextest never uses.
    """


class UnboundedTestError(TimeoutBudgetError):
    """Raised when a ``slow-timeout`` bounds nothing.

    ``terminate-after`` is optional, and nextest only terminates a test
    when it is set: `slow-timeout = "2m"` and
    `slow-timeout = { period = "2m" }` both mark a test slow after two
    minutes and then let it run for ever. Reading either as a two-minute
    budget reports tier one as present when it is absent, which is the
    inversion this contract exists to catch.
    """
