"""Guard the doctest paths in the Makefile against drift.

`PY_DOCTEST_PATHS` names what `--doctest-modules` collects, and the list
is written by hand. A module that gains an ``Examples`` section is
executed only if somebody remembers to cover it, so the example can go
untrue with no gate noticing. The contracts below are the reason that
cannot happen quietly.
"""

import pathlib
import re
import typing as typ

REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
MAKEFILE: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "Makefile"

#: Directories swept for docstring examples. Both are packages the
#: doctest lane is meant to cover: the library itself and the test
#: support modules, whose helpers are documented with examples too.
SWEPT: typ.Final[tuple[str, ...]] = ("python/stilyagi", "tests/support")

#: ``PY_DOCTEST_PATHS`` and any backslash continuations after it.
_ASSIGNMENT: typ.Final[re.Pattern[str]] = re.compile(
    r"^PY_DOCTEST_PATHS\s*\?=\s*((?:.*\\\n)*.*)$", re.MULTILINE
)


def _doctest_paths() -> frozenset[str]:
    """Read the paths `PY_DOCTEST_PATHS` names.

    Returns
    -------
    frozenset[str]
        Repository-relative paths, directories included. The read asserts
        the assignment exists, since its absence would leave every
        contract here asserting nothing.
    """
    match = _ASSIGNMENT.search(MAKEFILE.read_text(encoding="utf-8"))
    assert match is not None, "PY_DOCTEST_PATHS is not assigned in the Makefile"
    return frozenset(match.group(1).replace("\\\n", " ").split())


def _modules_with_examples() -> frozenset[pathlib.Path]:
    """Find every swept module carrying a docstring example.

    Returns
    -------
    frozenset[pathlib.Path]
        Paths relative to the repository root.
    """
    found: set[pathlib.Path] = set()
    for directory in SWEPT:
        for path in sorted((REPOSITORY_ROOT / directory).rglob("*.py")):
            if ">>>" in path.read_text(encoding="utf-8"):
                found.add(path.relative_to(REPOSITORY_ROOT))
    return frozenset(found)


def test_the_doctest_lane_runs_the_examples() -> None:
    """Assert the `test` recipe collects doctests from the named paths.

    Naming the variable is not enough: a recipe that never passes
    ``--doctest-modules`` leaves the list inert, which is the state this
    repository was in.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "--doctest-modules $(PY_DOCTEST_PATHS)" in makefile, (
        "the test recipe does not hand PY_DOCTEST_PATHS to --doctest-modules"
    )


def test_every_module_with_an_example_is_collected() -> None:
    """Assert the list in the Makefile covers every module with examples.

    A module is covered by its own name or by an ancestor directory the
    list names. The failure guarded against is a module gaining an
    example that nothing then executes.
    """
    collected = _doctest_paths()
    uncollected = sorted(
        str(module)
        for module in _modules_with_examples()
        if str(module) not in collected
        and not any(str(parent) in collected for parent in module.parents)
    )
    assert not uncollected, (
        "these modules carry docstring examples that PY_DOCTEST_PATHS does "
        f"not collect: {', '.join(uncollected)}"
    )


def test_the_list_names_no_path_that_is_gone() -> None:
    """Assert every named path still exists.

    A renamed or deleted path ends the whole lane rather than silently
    collecting less, which is the cheaper end of the same drift.
    """
    missing = sorted(
        path for path in _doctest_paths() if not (REPOSITORY_ROOT / path).exists()
    )
    assert not missing, f"PY_DOCTEST_PATHS names paths that do not exist: {missing}"


def test_the_sweep_finds_the_modules_that_carry_examples() -> None:
    """Assert the discovery is not empty, and names a module it must find.

    The two contracts above are both satisfied by a sweep returning
    nothing, so the sweep itself is pinned.
    """
    modules = _modules_with_examples()
    assert modules, "the sweep found no module carrying a docstring example"
    assert pathlib.Path("python/stilyagi/cli.py") in modules, (
        "the sweep missed a module known to carry examples"
    )
