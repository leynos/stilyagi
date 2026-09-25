"""Unit tests for the Rust bridge vocabulary sync and error translation."""

import concurrent.futures
import json
import logging
import threading
import typing as typ

import pytest
import stilyagi.engine.extraction as extraction_module
from stilyagi import engine, model

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from syrupy.assertion import SnapshotAssertion

pytest_plugins = ("tests.package_skeleton_support",)
pytestmark = pytest.mark.usefixtures("reset_extraction_state")


def test_engine_bridge_syntax_spellings_match_the_python_enum() -> None:
    """Keep the Python enum and the Rust bridge syntax spellings aligned."""
    from stilyagi._stilyagi_rs import supported_syntaxes

    assert_with_context(
        supported_syntaxes()
        == (
            model.Syntax.MARKDOWN.value,
            model.Syntax.PYTHON_DOCSTRING.value,
            model.Syntax.RUST_DOC_COMMENT.value,
        ),
        "expected supported_syntaxes() == (model.Syntax.MARKD...",
    )


def test_engine_bridge_region_kind_spellings_match_the_rust_ir_vocab(
    snapshot: SnapshotAssertion,
) -> None:
    """Expose the canonical Rust IR region kind spellings to Python."""
    assert_with_context(
        engine.supported_region_kinds() == snapshot,
        "expected the bridge region vocabulary to match its r...",
    )


def test_extraction_state_reset_refreshes_region_kind_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh lazy region-kind caches when tests patch the Rust bridge."""
    with monkeypatch.context() as patch:
        patch.setattr(
            extraction_module,
            "bridge_supported_region_kinds",
            lambda: ("first_kind",),
        )
        extraction_module.reset_extraction_state_for_tests()
        assert_with_context(
            extraction_module.supported_region_kinds() == ("first_kind",),
            "expected extraction_module.supported_region_kinds() ...",
        )

        patch.setattr(
            extraction_module,
            "bridge_supported_region_kinds",
            lambda: ("second_kind",),
        )
        assert_with_context(
            extraction_module.supported_region_kinds() == ("first_kind",),
            "expected extraction_module.supported_region_kinds() ...",
        )

        extraction_module.reset_extraction_state_for_tests()
        assert_with_context(
            extraction_module.supported_region_kinds() == ("second_kind",),
            "expected extraction_module.supported_region_kinds() ...",
        )


def test_syntax_vocab_validation_is_resettable_for_bridge_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset one-time syntax validation when tests patch bridge vocabularies."""
    supported = (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    )

    with monkeypatch.context() as patch:
        patch.setattr(extraction_module, "bridge_supported_syntaxes", lambda: supported)
        extraction_module.reset_extraction_state_for_tests()
        extraction_module._validate_syntax_vocab_once()

        patch.setattr(
            extraction_module, "bridge_supported_syntaxes", lambda: ("drift",)
        )
        extraction_module._validate_syntax_vocab_once()

        extraction_module.reset_extraction_state_for_tests()
        with pytest.raises(
            RuntimeError, match="Python and Rust syntax spellings differ"
        ):
            extraction_module._validate_syntax_vocab_once()


def test_syntax_vocab_validation_is_shared_by_concurrent_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate bridge syntax vocabulary once across concurrent callers."""
    call_count = 0
    call_count_lock = threading.Lock()
    supported = (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    )

    def bridge_supported_syntaxes() -> tuple[str, ...]:
        """Return supported syntax spellings while counting bridge calls."""
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        return supported

    monkeypatch.setattr(
        extraction_module, "bridge_supported_syntaxes", bridge_supported_syntaxes
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(extraction_module._validate_syntax_vocab_once)
            for _ in range(8)
        ]
        for future in futures:
            future.result()

    assert call_count == 1, "expected call_count == 1"


@pytest.mark.parametrize(
    "bridge_error",
    [
        pytest.param(NotImplementedError, id="unsupported-syntax"),
        pytest.param(ValueError, id="unknown-syntax"),
        pytest.param(RuntimeError, id="parser-or-ir-failure"),
    ],
)
def test_extract_bridge_payload_translates_documented_bridge_errors(
    monkeypatch: pytest.MonkeyPatch,
    bridge_error: type[Exception],
) -> None:
    """Translate only the documented Rust bridge error types at its boundary."""
    message = "bridge exploded"

    def fail_bridge(_source: str, _syntax: str) -> typ.NoReturn:
        """Raise one documented bridge failure."""
        raise bridge_error(message)

    monkeypatch.setattr(extraction_module, "extract_document_bridge", fail_bridge)

    with pytest.raises(extraction_module.BridgeExtractionError, match=message) as error:
        extraction_module._extract_bridge_payload("# Heading", model.Syntax.MARKDOWN)

    assert isinstance(error.value.__cause__, bridge_error), "expected bridge cause"


@pytest.mark.parametrize(
    ("extract_document", "expected_warning_args"),
    [
        pytest.param(
            engine.extract_document,
            ("stilyagi.engine.extract_document", 0, "future_kind"),
            id="public-engine-boundary",
        ),
        pytest.param(
            extraction_module.extract_document,
            None,
            id="read-only-extraction-adapter",
        ),
    ],
)
def test_extract_document_preserves_unknown_ir_region_kind(
    caplog: pytest.LogCaptureFixture,
    extract_document: cabc.Callable[[str, model.Syntax], model.Document],
    expected_warning_args: tuple[str, int, str] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve unknown IR kinds and only warn at the public command boundary."""

    def bridge_payload(source: str, syntax: str) -> dict[str, object]:
        """Return a bridge payload with a future IR kind."""
        assert source == "Example", "expected source == 'Example'"
        assert_with_context(
            syntax == model.Syntax.MARKDOWN.value,
            "expected syntax == model.Syntax.MARKDOWN.value",
        )
        return {
            "syntax": syntax,
            "regions": [],
            "ir_json": json.dumps({
                "schema_version": "1.1.0",
                "regions": [{"kind": "future_kind", "text": "Example"}],
            }),
        }

    monkeypatch.setattr(extraction_module, "extract_document_bridge", bridge_payload)
    caplog.set_level(logging.WARNING, logger="stilyagi.engine.extraction")

    document = extract_document("Example", model.Syntax.MARKDOWN)

    assert document.ir is not None, "expected document.ir is not None"
    assert_with_context(
        document.ir["regions"] == [{"kind": "future_kind", "text": "Example"}],
        "expected document.ir['regions'] == [<'kind': 'future...",
    )
    records = [
        record
        for record in caplog.records
        if record.name == "stilyagi.engine.extraction"
    ]
    if expected_warning_args is None:
        assert records == [], "expected records == []"
    else:
        assert len(records) == 1, "expected len(records) == 1"
        assert_with_context(
            records[0].message
            == (
                "Unknown IR region kind from Rust bridge during "
                "stilyagi.engine.extract_document: index=0 kind='future_kind'"
            ),
            'expected records[0].message == "Unknown IR region ki...',
        )
        assert_with_context(
            records[0].args == expected_warning_args,
            "expected records[0].args == expected_warning_args",
        )
