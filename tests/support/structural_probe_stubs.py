"""Test doubles shared by the structural probe's test modules.

Both the command-line tests and the injected-dependency tests drive the probe
through a subprocess runner they control, and both need a request carrying
source text that was never written to disk. Keeping one runner and one request
factory here means the two modules cannot drift into testing different
protocol shapes, which is exactly the failure a near-copy invites.
"""

import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: constructing the CompletedProcess results a stub runner must return
import typing as typ

from stilyagi import model

from tests.performance import structural_probe_boundary as boundary

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: Repository root, derived from this file's location rather than the cwd.
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
#: The Markdown fixture request factory's path, absolute and repository-rooted.
MARKDOWN_PATH = REPOSITORY_ROOT / boundary.MARKDOWN_FIXTURE

#: Synthetic source that exists only in memory, so a test cannot silently pass
#: by reading the real fixture off disk.
SYNTHETIC_SOURCE = "# Synthetic heading\n\nBody text.\n"

#: Child output reporting an integer duration, the protocol's happy path.
CHILD_JSON = '{"duration_ns": 7}'


class StubRunner:
    """A subprocess runner that records its calls and returns canned output.

    Parameters
    ----------
    stdout:
        Text the stub reports on standard output. Ignored when ``error`` is
        set, because a failing child never reports parsed output.
    error:
        Exception raised instead of returning, modelling a child that fails.

    Examples
    --------
    >>> StubRunner(stdout='{"duration_ns": 3}')(["python"]).returncode
    0
    """

    def __init__(
        self,
        stdout: str = CHILD_JSON,
        error: BaseException | None = None,
    ) -> None:
        """Record the canned output and the failure to raise, if any."""
        self.stdout = stdout
        self.error = error
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(
        self,
        argv: cabc.Sequence[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Record one invocation and return the canned result."""
        self.calls.append((list(argv), kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(list(argv), 0, stdout=self.stdout)


def markdown_fixture_request() -> boundary.ProbeRequest:
    """Return a Markdown request carrying synthetic, in-memory source.

    Returns
    -------
    boundary.ProbeRequest
        A request whose source never existed on disk.

    Examples
    --------
    >>> markdown_fixture_request().source.startswith("# Synthetic")
    True
    """
    return boundary.ProbeRequest(
        path=MARKDOWN_PATH,
        source=SYNTHETIC_SOURCE,
        syntax=model.Syntax.MARKDOWN,
        byte_count=len(SYNTHETIC_SOURCE.encode()),
    )
