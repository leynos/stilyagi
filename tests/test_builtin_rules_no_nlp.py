"""Prove the starter-pack builtins run without importing NLP packages.

The roadmap requires that the deterministic rules never reach for NLP
services. Asserting ``"spacy" not in sys.modules`` inside the test process
would be affected by whatever other tests imported first, so the check runs in
a fresh interpreter whose import machinery refuses the packages outright: an
accidental import becomes an immediate failure rather than a silent cost.

The command-level guard blocks the same packages from a ``sitecustomize``
module that also leaves a marker file behind. A marker is what catches an
import wrapped in ``try``/``except ImportError``: the command would still
succeed through its fallback path, so only the attempt's own evidence shows
that the rules paid for an NLP dependency they must not need.
"""

import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the probes run a trusted local interpreter.
import sys

from tests.support.subprocess_env import python_module_environment

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Packages that must never be imported by the deterministic builtin rules.
_NLP_ROOTS = ("en_core_web_sm", "spacy", "spacy_lookups_data")

_PROBE = """
import sys

BLOCKED = {blocked!r}


class BlockNlp:
    \"\"\"Refuse every NLP package import for the lifetime of this probe.\"\"\"

    def find_spec(self, fullname, path=None, target=None):
        \"\"\"Raise for a blocked package, defer for everything else.\"\"\"
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError(f"{{fullname}} is blocked for this probe")
        return None


sys.meta_path.insert(0, BlockNlp())

from stilyagi import config, engine, model
from stilyagi.config.schema import LintConfig
from stilyagi.rules.registry import RuleRunRequest, run_rules

source = "# Start\\n### Detail the the obviously\\n"
request = RuleRunRequest(
    config=config.StilyagiConfig(
        lint=LintConfig(select=("MD", "STY", "TERM")),
        rules={{"TERM001": {{"terms": ["obviously"]}}}},
    ),
    config_path=None,
    source_bytes=source.encode("utf-8"),
    reported_path="doc.md",
    document=engine.extract_document(source, model.Syntax.MARKDOWN),
)

produced = run_rules(request)
assert [item.code for item in produced] == ["MD001", "STY001", "TERM001"], produced
loaded = sorted(
    name for name in sys.modules if name.split(".")[0] in BLOCKED
)
assert not loaded, loaded
print("ok")
"""

_SITECUSTOMIZE = """
import pathlib
import sys

BLOCKED = {blocked!r}
MARKER = pathlib.Path(__file__).with_name("blocked-import.txt")


class BlockNlp:
    \"\"\"Refuse NLP packages and record every attempt to import one.\"\"\"

    def find_spec(self, fullname, path=None, target=None):
        \"\"\"Raise for a blocked package, defer for everything else.\"\"\"
        if fullname.split(".")[0] in BLOCKED:
            MARKER.write_text(fullname, encoding="utf-8")
            raise ImportError(f"{{fullname}} is blocked for this probe")
        return None


sys.meta_path.insert(0, BlockNlp())
"""


def _run_probe(
    argv: list[str],
    *,
    cwd: pathlib.Path,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one probe interpreter and capture its streams as text."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed probe, no shell.
        argv,
        cwd=cwd,
        env=env or python_module_environment(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_builtin_rules_never_import_spacy() -> None:
    """A full rule run succeeds with the NLP packages blocked."""
    completed = _run_probe(
        [sys.executable, "-c", _PROBE.format(blocked=_NLP_ROOTS)],
        cwd=REPOSITORY_ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok", "expected the probe to print ok"


def test_the_check_command_never_imports_an_nlp_package(tmp_path: pathlib.Path) -> None:
    """The real command path succeeds without even attempting an NLP import."""
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    (probe_dir / "sitecustomize.py").write_text(
        _SITECUSTOMIZE.format(blocked=_NLP_ROOTS),
        encoding="utf-8",
    )
    marker = probe_dir / "blocked-import.txt"

    env = python_module_environment()
    env["PYTHONPATH"] = os.pathsep.join((str(probe_dir), env["PYTHONPATH"]))
    completed = _run_probe(
        [
            sys.executable,
            "-m",
            "stilyagi",
            "check",
            "-",
            "--stdin-filename",
            "notes.md",
        ],
        cwd=tmp_path,
        env=env,
        stdin="the the.\n",
    )

    assert completed.returncode == 0, completed.stderr
    assert "STY001" in completed.stdout, (
        f"expected the run to exercise the text rules, got {completed.stdout!r}"
    )
    assert not marker.exists(), (
        f"expected no NLP import attempt, got {marker.read_text(encoding='utf-8')}"
    )
