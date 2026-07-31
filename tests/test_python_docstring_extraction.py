"""Python-facing tests for owner-aware docstring extraction."""

import json
import keyword
import pathlib
import typing as typ

import hypothesis as hyp
import hypothesis.strategies as st
from pytest_bdd import given, scenario, then, when
from stilyagi import engine, model
from syrupy.extensions.json import JSONSnapshotExtension

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from syrupy.assertion import SnapshotAssertion


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARED_PYTHON_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/python/valid/module-class-function-docstrings.py",
)
MALFORMED_PYTHON_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/python/malformed/unclosed-function.py.txt",
)
# This path is insta's auto-generated snapshot filename, derived from the Rust
# test name ``shared_python_fixture_has_a_golden_ir_snapshot`` in
# ``crates/stilyagi-extract/tests/extract/ir_identity.rs``. Renaming or moving
# that Rust test changes the generated snapshot name, which would break
# ``test_python_docstring_ir_matches_reviewed_rust_snapshot`` with a
# ``FileNotFoundError``; keep the two in sync.
RUST_PYTHON_SNAPSHOT = pathlib.Path(
    "crates/stilyagi-extract/tests/extract/snapshots/"
    "extract_integration__ir_identity__extraction_tests__shared_python_fixture_has_a_golden_ir_snapshot.snap",
)


class PythonDocstringState(typ.TypedDict):
    """Scenario state for Python docstring extraction behaviour."""

    source: str
    document: model.Document | None


@scenario(
    "../features/stilyagi_python_docstring_extraction.feature",
    "Extract Python docstrings with owner metadata",
)
def test_extract_python_docstrings_with_owner_metadata() -> None:
    """Run the owner-aware Python docstring extraction scenario."""


@scenario(
    "../features/stilyagi_python_docstring_extraction.feature",
    "Recover from malformed Python through the Python engine",
)
def test_recover_from_malformed_python_through_the_python_engine() -> None:
    """Run the malformed Python recovery scenario."""


@given(
    "the shared Python docstring fixture is available",
    target_fixture="python_docstring_state",
)
def shared_python_docstring_fixture_is_available() -> PythonDocstringState:
    """Read the shared valid Python fixture into scenario state."""
    return {
        "source": _fixture_source(SHARED_PYTHON_FIXTURE),
        "document": None,
    }


@given(
    "the malformed Python docstring fixture is available",
    target_fixture="python_docstring_state",
)
def malformed_python_docstring_fixture_is_available() -> PythonDocstringState:
    """Read the malformed Python fixture into scenario state."""
    return {
        "source": _fixture_source(MALFORMED_PYTHON_FIXTURE),
        "document": None,
    }


@when("I extract Python docstrings through the Python engine")
def extract_python_docstrings_through_the_python_engine(
    python_docstring_state: PythonDocstringState,
) -> None:
    """Run the public Python engine extraction adapter."""
    python_docstring_state["document"] = engine.extract_document(
        python_docstring_state["source"],
        model.Syntax.PYTHON_DOCSTRING,
    )


@then("the Python document contains docstring regions")
def python_document_contains_docstring_regions(
    python_docstring_state: PythonDocstringState,
) -> None:
    """Assert the typed Python region surface."""
    document = _scenario_document(python_docstring_state)

    assert document.syntax is model.Syntax.PYTHON_DOCSTRING, "Document syntax mismatch"
    assert [region.kind for region in document.regions] == [
        "python_docstring",
        "python_docstring",
        "python_docstring",
        "python_docstring",
    ], "Region kinds do not match expected"
    assert [region.text for region in document.regions] == [
        "Module docstring for the shared Stilyagi corpus.",
        "Class docstring with prose for extraction tests.",
        "Return a documented value from a method docstring.",
        "Use a function docstring for later Python extraction slices.",
    ], "Region texts do not match expected"


@then("the Python IR records owner metadata")
def python_ir_records_owner_metadata(
    python_docstring_state: PythonDocstringState,
) -> None:
    """Assert owner metadata parsed from the bridge IR payload."""
    regions = _python_docstring_ir_regions(_scenario_ir(python_docstring_state))

    assert [_owner_tuple(region) for region in regions] == [
        ("module", None, None),
        ("class", "FixtureExample", "FixtureExample"),
        ("function", "method", "FixtureExample.method"),
        ("function", "fixture_function", "fixture_function"),
    ], "Owner metadata does not match expected"


@then("the Python document contains the module docstring")
def python_document_contains_the_module_docstring(
    python_docstring_state: PythonDocstringState,
) -> None:
    """Assert malformed extraction preserves the module docstring only."""
    document = _scenario_document(python_docstring_state)

    assert [region.text for region in document.regions] == [
        "Module docstring before malformed Python source.",
    ], "Malformed document regions do not match expected"


@then("the Python IR records a recoverable parse error")
def python_ir_records_a_recoverable_parse_error(
    python_docstring_state: PythonDocstringState,
) -> None:
    """Assert malformed extraction records tree-sitter recovery diagnostics."""
    ir = _scenario_ir(python_docstring_state)
    errors = typ.cast("list[dict[str, JSONType]]", ir["errors"])

    assert errors, "Expected recoverable parse errors"
    assert {error["code"] for error in errors} == {
        "python-parse-recovery",
    }, "Recoverable parse error codes do not match expected"


def test_python_docstring_ir_matches_reviewed_rust_snapshot() -> None:
    """Keep Python IR adaptation aligned with the reviewed Rust snapshot."""
    source = _fixture_source(SHARED_PYTHON_FIXTURE)
    document = engine.extract_document(source, model.Syntax.PYTHON_DOCSTRING)
    rust_snapshot = _load_insta_json_snapshot(REPOSITORY_ROOT / RUST_PYTHON_SNAPSHOT)

    assert document.ir is not None, "expected document.ir is not None"
    assert _normalize_python_ir(document.ir) == _normalize_python_ir(rust_snapshot), (
        "expected _normalize_python_ir(document.ir) == _norma..."
    )


def test_shared_python_fixture_ir_matches_json_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the Python-parsed IR contract for the shared fixture."""
    source = _fixture_source(SHARED_PYTHON_FIXTURE)
    document = engine.extract_document(source, model.Syntax.PYTHON_DOCSTRING)

    assert document.ir is not None, "expected document.ir is not None"
    assert _normalize_python_ir(document.ir) == snapshot(
        extension_class=JSONSnapshotExtension,
    ), "expected _normalize_python_ir(document.ir) == snapsh..."


@hyp.given(
    name=st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True).filter(
        lambda value: not keyword.iskeyword(value),
    ),
    body=st.text(
        alphabet=st.characters(
            blacklist_characters='"\n\\',
            blacklist_categories=("Cc", "Cs"),
        ),
        min_size=1,
        max_size=64,
    ),
)
def test_generated_function_docstrings_preserve_owner_and_text(
    name: str,
    body: str,
) -> None:
    """Extract fixed-shape generated functions without changing Python syntax."""
    source = f'def {name}():\n    """{body}"""\n'
    document = engine.extract_document(source, model.Syntax.PYTHON_DOCSTRING)

    assert [region.text for region in document.regions] == [body], (
        "expected [region.text for region in document.regions..."
    )
    region = _python_docstring_ir_regions(_require_ir(document))[0]
    assert _owner_tuple(region) == ("function", name, name), (
        "expected _owner_tuple(region) == ('function', name, ..."
    )


def _fixture_source(relative_path: pathlib.Path) -> str:
    """Read a repository fixture as UTF-8 text."""
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _scenario_document(state: PythonDocstringState) -> model.Document:
    """Return the extracted document from BDD scenario state."""
    document = state["document"]
    assert document is not None, "expected document is not None"
    return document


def _scenario_ir(state: PythonDocstringState) -> cabc.Mapping[str, JSONType]:
    """Return the parsed IR from BDD scenario state."""
    return _require_ir(_scenario_document(state))


def _require_ir(document: model.Document) -> cabc.Mapping[str, JSONType]:
    """Return a document IR payload, failing if it is absent."""
    assert document.ir is not None, "expected document.ir is not None"
    return typ.cast("cabc.Mapping[str, JSONType]", document.ir)


def _python_docstring_ir_regions(
    ir: cabc.Mapping[str, JSONType],
) -> list[dict[str, JSONType]]:
    """Return Python docstring regions from an IR payload."""
    regions = typ.cast("list[dict[str, JSONType]]", ir["regions"])
    return [region for region in regions if region["kind"] == "python_docstring"]


def _owner_tuple(
    region: cabc.Mapping[str, JSONType],
) -> tuple[str, str | None, str | None]:
    """Return a stable owner tuple from an IR region."""
    owner = typ.cast("dict[str, JSONType]", region["owner"])
    return (
        typ.cast("str", owner["kind"]),
        typ.cast("str | None", owner["name"]),
        typ.cast("str | None", owner["qualname"]),
    )


def _load_insta_json_snapshot(path: pathlib.Path) -> dict[str, JSONType]:
    """Load the JSON payload stored after an insta snapshot metadata header."""
    _header, json_payload = path.read_text(encoding="utf-8").split(
        "\n---\n", maxsplit=1
    )
    parsed = json.loads(json_payload)
    assert isinstance(parsed, dict), "expected isinstance(parsed, dict)"
    return typ.cast("dict[str, JSONType]", parsed)


def _normalize_python_ir(ir: cabc.Mapping[str, JSONType]) -> dict[str, JSONType]:
    """Normalize volatile producer and source-identity fields for snapshots."""
    normalized = json.loads(json.dumps(ir))
    assert isinstance(normalized, dict), "expected isinstance(normalized, dict)"

    document = typ.cast("dict[str, JSONType]", normalized["document"])
    document["content_hash"] = "<content-hash>"
    document["path"] = "<normalized>"
    document["uri"] = "<normalized>"

    for producer in typ.cast("list[dict[str, JSONType]]", normalized["producers"]):
        if producer["name"] == "tree-sitter-python":
            producer["version"] = "<tree-sitter-python-version>"

    return typ.cast("dict[str, JSONType]", normalized)
