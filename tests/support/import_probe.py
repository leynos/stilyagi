"""Fresh-interpreter probe that reports import-time execution side effects.

The rule-discovery commands answer from static declarations. Proving that
means observing a real interpreter start, not only an in-process test: a
module imported by the command line could read configuration, extract a
document, tokenize text, consult plugin entry points, or write a cache entry
before any test sentinel exists.

The probe installs three independent guards before importing `stilyagi.cli`:

- an audit hook records every file operation under the project directory, so
  a read whose exception is swallowed is still visible;
- a meta-path loader wraps each execution module and installs its sentinels as
  soon as the module body finishes, before the importing module resumes; and
- a trace function runs during each protected module's own execution, so a
  protected function the module calls while defining itself is recorded too.

Any recorded effect makes the probe exit non-zero with a single report line.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import] - trusted local interpreter.
import sys
import typing as typ

from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import pathlib

PROBE_SETUP = """\
import importlib.abc
import importlib.metadata
import os
import sys

root = os.path.realpath(os.getcwd())
side_effects = []

# The probe's own fixture modules may live beside the project; the
# interpreter's bytecode cache write is not the rule execution this proves.
sys.dont_write_bytecode = True


def _watch(event, args):
    if event not in {"open", "os.mkdir", "os.rename", "os.remove", "os.rmdir"}:
        return
    first = args[0] if args else None
    if not isinstance(first, (str, bytes, os.PathLike)):
        return
    path = os.path.realpath(os.fsdecode(first))
    if path == root or path.startswith(root + os.sep):
        side_effects.append((event, path))


def _forbidden(name):
    def note(*args, **kwargs):
        side_effects.append(("call", name))

    return note


_TARGETS = {
    "stilyagi.config.resolve": ("load_config_table",),
    "stilyagi.discovery": ("discover_files",),
    "stilyagi.engine": ("extract_document",),
    "stilyagi.rules.builtin.pack": ("run_selected",),
    "stilyagi.rules.builtin.text": ("tokenize_segments",),
    "stilyagi.rules.registry": ("run_rules",),
}

_guarding = False


def _guard_calls(frame, event, arg):
    if not _guarding:
        return None
    if event != "call":
        return _guard_calls
    name = frame.f_code.co_name
    module = frame.f_globals.get("__name__")
    if module in _TARGETS and name in _TARGETS[module]:
        side_effects.append(("call", name))
    return _guard_calls


class _SentinelLoader(importlib.abc.Loader):
    def __init__(self, inner, fullname):
        self._inner = inner
        self._fullname = fullname

    def create_module(self, spec):
        create = getattr(self._inner, "create_module", None)
        return None if create is None else create(spec)

    def exec_module(self, module):
        # Guard calls made from inside the module's own body as well as
        # calls made by later importers; the post-exec attribute swap alone
        # would miss a function the module calls while defining itself.
        global _guarding
        previous = _guarding
        _guarding = True
        try:
            sys.settrace(_guard_calls)
            self._inner.exec_module(module)
        finally:
            sys.settrace(None)
            _guarding = previous
        for attribute in _TARGETS[self._fullname]:
            setattr(module, attribute, _forbidden(attribute))


class _SentinelFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _TARGETS:
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            find = getattr(finder, "find_spec", None)
            if find is None:
                continue
            spec = find(fullname, path, target)
            if spec is not None:
                break
        else:
            return None
        spec.loader = _SentinelLoader(spec.loader, fullname)
        return spec


sys.addaudithook(_watch)
sys.meta_path.insert(0, _SentinelFinder())
importlib.metadata.entry_points = _forbidden("entry_points")
"""

PROBE_EPILOGUE = """
if side_effects:
    raise SystemExit(f"import side effects: {side_effects!r}")
"""


def run_import_probe(
    root: pathlib.Path,
    *,
    before_cli: str = "",
    after_cli: str = "",
    extra_targets: dict[str, tuple[str, ...]] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Import the command line in a fresh interpreter and detect side effects.

    Parameters
    ----------
    root
        Project directory used as the working directory. Every file operation
        beneath it is recorded by the audit hook.
    before_cli
        Statements run before `stilyagi.cli` is imported, for controls that
        must act during the import phase.
    after_cli
        Statements run after `stilyagi.cli` is imported and before the report.
    extra_targets
        Additional ``module: (function, ...)`` pairs to protect, for controls
        that use a synthetic module.

    Returns
    -------
    subprocess.CompletedProcess[bytes]
        Captured process status, standard output, and standard error. Exit
        status zero means no side effect was observed.

    Examples
    --------
    >>> import pathlib
    >>> root = pathlib.Path("tests/fixtures/import-probe")
    >>> run_import_probe(root).returncode  # doctest: +SKIP
    0
    """
    targets = f"_TARGETS.update({extra_targets!r})\n" if extra_targets else ""
    script = (
        f"{PROBE_SETUP}{targets}{before_cli}\nimport stilyagi.cli\n{after_cli}\n"
        f"{PROBE_EPILOGUE}"
    )
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, "-c", script],
        cwd=root,
        env=python_module_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=60,
    )
