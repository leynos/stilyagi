"""Prove the starter-pack builtins run without importing spaCy.

The roadmap requires that the deterministic rules never reach for NLP
services. Asserting ``"spacy" not in sys.modules`` inside the test process
would be affected by whatever other tests imported first, so the check runs in
a fresh interpreter whose import machinery refuses spaCy outright: an
accidental import becomes an immediate failure rather than a silent cost.
"""

import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the probe runs a trusted local interpreter.
import sys

from tests.support.subprocess_env import python_module_environment

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]

_PROBE = """
import sys


class BlockSpacy:
    \"\"\"Refuse every spaCy import for the lifetime of this probe.\"\"\"

    def find_spec(self, fullname, path=None, target=None):
        \"\"\"Raise for spaCy modules, defer for everything else.\"\"\"
        if fullname == "spacy" or fullname.startswith("spacy."):
            raise ImportError(f"{fullname} is blocked for this probe")
        return None


sys.meta_path.insert(0, BlockSpacy())

from stilyagi import config, engine, model
from stilyagi.config.schema import LintConfig
from stilyagi.rules.registry import RuleRunRequest, run_rules

source = "# Start\\n### Detail the the obviously\\n"
request = RuleRunRequest(
    config=config.StilyagiConfig(
        lint=LintConfig(select=("MD", "STY", "TERM")),
        rules={"TERM001": {"terms": ["obviously"]}},
    ),
    config_path=None,
    source_bytes=source.encode("utf-8"),
    reported_path="doc.md",
    document=engine.extract_document(source, model.Syntax.MARKDOWN),
)

produced = run_rules(request)
assert [item.code for item in produced] == ["MD001", "STY001", "TERM001"], produced
loaded = sorted(name for name in sys.modules if "spacy" in name)
assert not loaded, loaded
print("ok")
"""


def test_builtin_rules_never_import_spacy() -> None:
    """A full rule run succeeds with spaCy blocked at the import system."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed probe, no shell.
        [sys.executable, "-c", _PROBE],
        cwd=REPOSITORY_ROOT,
        env=python_module_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok", "expected the probe to print ok"
