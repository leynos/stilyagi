"""Rust-facing tests for owner-aware doc-comment extraction."""

import keyword
import pathlib
import typing as typ

import hypothesis as hyp
import hypothesis.strategies as st
from pytest_bdd import given, scenario, then, when
from stilyagi import engine, model
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.ir_identity import load_insta_json_snapshot, normalize_ir_identity

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from syrupy.assertion import SnapshotAssertion


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARED_RUST_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/rust/valid/item-doc-comments.rs",
)
ATTRIBUTE_RUST_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/rust/valid/item-doc-comments-with-attributes.rs",
)
MALFORMED_RUST_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/rust/malformed/unclosed-item.rs",
)
RUST_IR_SNAPSHOT = pathlib.Path(
    "crates/stilyagi-extract/tests/extract/snapshots/"
    "extract_integration__ir_identity__extraction_tests__shared_rust_fixture_has_a_golden_ir_snapshot.snap",
)


class RustDocCommentState(typ.TypedDict):
    """Scenario state for Rust doc-comment extraction behaviour."""

    source: str
    document: model.Document | None


@scenario(
    "../features/stilyagi_rust_doc_comment_extraction.feature",
    "Extract documentation comments with their owning items",
)
def test_extract_rust_doc_comments_with_owner_metadata() -> None:
    """Run the owner-aware Rust doc-comment extraction scenario."""


@scenario(
    "../features/stilyagi_rust_doc_comment_extraction.feature",
    "Recover from a malformed Rust file",
)
def test_recover_from_a_malformed_rust_file() -> None:
    """Run the malformed Rust recovery scenario."""


@given(
    "the shared Rust doc-comment fixture is available",
    target_fixture="rust_doc_comment_state",
)
def shared_rust_doc_comment_fixture_is_available() -> RustDocCommentState:
    """Read the shared valid Rust fixture into scenario state."""
    return {
        "source": _fixture_source(SHARED_RUST_FIXTURE),
        "document": None,
    }


@given(
    "the malformed Rust doc-comment fixture is available",
    target_fixture="rust_doc_comment_state",
)
def malformed_rust_doc_comment_fixture_is_available() -> RustDocCommentState:
    """Read the malformed Rust fixture into scenario state."""
    return {
        "source": _fixture_source(MALFORMED_RUST_FIXTURE),
        "document": None,
    }


@when("I extract Rust doc comments through the Python engine")
def extract_rust_doc_comments_through_the_python_engine(
    rust_doc_comment_state: RustDocCommentState,
) -> None:
    """Run the public Python engine extraction adapter."""
    rust_doc_comment_state["document"] = engine.extract_document(
        rust_doc_comment_state["source"],
        model.Syntax.RUST_DOC_COMMENT,
    )


@then("the Rust document contains doc-comment regions")
def rust_document_contains_doc_comment_regions(
    rust_doc_comment_state: RustDocCommentState,
) -> None:
    """Assert the typed Rust region surface."""
    document = _scenario_document(rust_doc_comment_state)

    assert document.syntax is model.Syntax.RUST_DOC_COMMENT
    assert [region.kind for region in document.regions] == [
        "rust_doc_comment",
        "rust_doc_comment",
        "rust_doc_comment",
        "rust_doc_comment",
    ]
    assert [region.text for region in document.regions] == [
        " Crate-level documentation comment for the shared Stilyagi corpus.",
        " Item-level documentation comment used by later Rust extraction slices.",
        " Method documentation comment with extractable prose.",
        " Function documentation comment after a suppression marker.",
    ]


@then("the Rust IR records owner metadata")
def rust_ir_records_owner_metadata(rust_doc_comment_state: RustDocCommentState) -> None:
    """Assert owner metadata parsed from the bridge IR payload."""
    regions = _rust_doc_comment_ir_regions(_scenario_ir(rust_doc_comment_state))

    assert [_owner_tuple(region) for region in regions] == [
        ("module", None, None),
        ("struct", "FixtureExample", "FixtureExample"),
        (
            "function",
            "documented_value",
            "FixtureExample::documented_value",
        ),
        ("function", "fixture_function", "fixture_function"),
    ]


@then("the Rust document contains the crate doc-comment")
def rust_document_contains_the_crate_doc_comment(
    rust_doc_comment_state: RustDocCommentState,
) -> None:
    """Assert malformed extraction preserves the crate doc-comment only."""
    document = _scenario_document(rust_doc_comment_state)

    assert [region.text for region in document.regions] == [
        " Crate-level documentation before malformed Rust source.",
    ]


@then("the Rust IR records a recoverable parse error")
def rust_ir_records_a_recoverable_parse_error(
    rust_doc_comment_state: RustDocCommentState,
) -> None:
    """Assert malformed extraction records tree-sitter recovery diagnostics."""
    ir = _scenario_ir(rust_doc_comment_state)
    errors = typ.cast("list[dict[str, JSONType]]", ir["errors"])

    assert errors
    assert {error["code"] for error in errors} == {
        "rust-doc-comment-error-subtree",
        "rust-parse-recovery",
    }


def test_rust_doc_comment_ir_matches_reviewed_rust_snapshot() -> None:
    """Keep Python IR adaptation aligned with the reviewed Rust snapshot."""
    source = _fixture_source(SHARED_RUST_FIXTURE)
    document = engine.extract_document(source, model.Syntax.RUST_DOC_COMMENT)
    rust_snapshot = load_insta_json_snapshot(REPOSITORY_ROOT / RUST_IR_SNAPSHOT)

    assert document.ir is not None
    assert normalize_ir_identity(
        document.ir,
        producer_name="tree-sitter-rust",
        producer_version_placeholder="<tree-sitter-rust-version>",
    ) == normalize_ir_identity(
        rust_snapshot,
        producer_name="tree-sitter-rust",
        producer_version_placeholder="<tree-sitter-rust-version>",
    )


def test_shared_rust_fixture_ir_matches_json_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the Python-parsed IR contract for the shared Rust fixture."""
    source = _fixture_source(SHARED_RUST_FIXTURE)
    document = engine.extract_document(source, model.Syntax.RUST_DOC_COMMENT)

    assert document.ir is not None
    assert normalize_ir_identity(
        document.ir,
        producer_name="tree-sitter-rust",
        producer_version_placeholder="<tree-sitter-rust-version>",
    ) == snapshot(
        extension_class=JSONSnapshotExtension,
    )


@hyp.given(
    name=st.from_regex(r"[A-Za-z_][A-Za-z0-9_]*", fullmatch=True).filter(
        lambda value: not keyword.iskeyword(value),
    ),
    body=st.text(
        alphabet=st.characters(
            blacklist_characters="\n\0",
            blacklist_categories=("Cc", "Cs"),
        ),
        min_size=1,
        max_size=64,
    ),
)
def test_generated_rust_doc_comments_preserve_owner_and_text(
    name: str,
    body: str,
) -> None:
    """Extract a fixed Rust function shape without changing the syntax."""
    source = f"/// {body}\npub fn {name}() {{}}\n"
    document = engine.extract_document(source, model.Syntax.RUST_DOC_COMMENT)

    assert [region.text for region in document.regions] == [f" {body}"]
    region = _rust_doc_comment_ir_regions(_require_ir(document))[0]
    assert _owner_tuple(region) == ("function", name, name)


def test_rust_doc_comments_survive_attribute_interleaving() -> None:
    """Extract a Rust struct document comment across attribute nodes."""
    source = _fixture_source(ATTRIBUTE_RUST_FIXTURE)
    document = engine.extract_document(source, model.Syntax.RUST_DOC_COMMENT)

    assert [region.text for region in document.regions] == [
        " Documentation comment that must attach to the struct, not the derive.",
    ]
    region = _rust_doc_comment_ir_regions(_require_ir(document))[0]
    assert _owner_tuple(region) == (
        "struct",
        "AttributeFixture",
        "attribute_fixture::AttributeFixture",
    )


def _fixture_source(relative_path: pathlib.Path) -> str:
    """Read a repository fixture as UTF-8 text."""
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _scenario_document(state: RustDocCommentState) -> model.Document:
    """Return the extracted document from BDD scenario state."""
    document = state["document"]
    assert document is not None
    return document


def _scenario_ir(state: RustDocCommentState) -> cabc.Mapping[str, JSONType]:
    """Return the parsed IR from BDD scenario state."""
    return _require_ir(_scenario_document(state))


def _require_ir(document: model.Document) -> cabc.Mapping[str, JSONType]:
    """Return a document IR payload, failing if it is absent."""
    assert document.ir is not None
    return typ.cast("cabc.Mapping[str, JSONType]", document.ir)


def _rust_doc_comment_ir_regions(
    ir: cabc.Mapping[str, JSONType],
) -> list[dict[str, JSONType]]:
    """Return Rust doc-comment regions from an IR payload."""
    regions = typ.cast("list[dict[str, JSONType]]", ir["regions"])
    return [region for region in regions if region["kind"] == "rust_doc_comment"]


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
