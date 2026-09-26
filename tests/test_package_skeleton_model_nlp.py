"""Unit tests for the model dataclasses and the NLP provider protocol.

These tests keep the placeholder model dataclasses' defaults predictable and
check the NLP provider protocol. Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_package_skeleton_model_nlp.py
"""

import typing as typ

import pytest
from stilyagi import model, nlp
from stilyagi.nlp import spacy_provider

from tests.support.assertions import assert_with_context

pytest_plugins = ("tests.package_skeleton_support",)
pytestmark = pytest.mark.usefixtures("reset_extraction_state")


def test_model_skeleton_dataclasses_preserve_defaults_and_children() -> None:
    """Keep the model placeholder dataclasses predictable."""
    region = model.Region(kind="paragraph", text="Hello")

    assert_with_context(
        not model.Document(syntax=model.Syntax.MARKDOWN).regions,
        "expected not model.Document(syntax=model.Syntax.MARK...",
    )
    assert_with_context(
        model.Document(syntax=model.Syntax.MARKDOWN).ir is None,
        "expected model.Document(syntax=model.Syntax.MARKDOWN...",
    )
    assert_with_context(
        model.Document(
            syntax=model.Syntax.MARKDOWN,
            regions=(region,),
        ).regions
        == (region,),
        "expected model.Document(syntax=model.Syntax.MARKDOWN...",
    )
    assert_with_context(
        model.Sentence(text="Hello world").text == "Hello world",
        "expected model.Sentence(text='Hello world').text == ...",
    )
    assert_with_context(
        model.Token(text="Hello").text == "Hello",
        "expected model.Token(text='Hello').text == 'Hello'",
    )


def test_spacy_provider_config_uses_the_default_model_name() -> None:
    """Apply the documented default spaCy model identifier."""
    assert_with_context(
        nlp.SpacyProviderConfig().model == "en_core_web_sm",
        "expected nlp.SpacyProviderConfig().model == 'en_core...",
    )


def test_spacy_provider_config_rejects_a_blank_model_name() -> None:
    """Reject a blank spaCy model identifier because it is unusable."""
    with pytest.raises(
        spacy_provider.InvalidSpacyModelError,
        match=r"^Invalid spaCy model: .*It must not be blank\.$",
    ):
        nlp.SpacyProviderConfig(model="")


@typ.runtime_checkable
class RuntimeCheckableNlpProvider(nlp.NlpProvider, typ.Protocol):
    """Runtime-checkable adapter for asserting the provider protocol shape."""


class DummyProvider:
    """Minimal object that satisfies the NLP provider protocol."""

    @property
    def provider_name(self) -> str:
        """The provider identifier.

        Returns
        -------
        str
            The ``dummy`` provider identifier.
        """
        return "dummy"


def test_nlp_provider_protocol_accepts_matching_provider_objects() -> None:
    """Accept objects that satisfy the NLP provider protocol."""
    assert_with_context(
        isinstance(DummyProvider(), RuntimeCheckableNlpProvider),
        "expected isinstance(DummyProvider(), RuntimeCheckabl...",
    )
