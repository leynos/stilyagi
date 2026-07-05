"""Unit tests for the ``typos.toml`` generator script.

The generator is a standalone ``uv run`` script rather than a package
module, so it is loaded here through ``importlib`` from its file path.
"""

import importlib.util
import pathlib
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import types

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "generate_typos_config.py"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(name="generator", scope="module")
def generator_fixture() -> types.ModuleType:
    """Load the generator script as a module from its file path."""
    spec = importlib.util.spec_from_file_location("generate_typos_config", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_config_emits_every_stem_and_suffix_pair(
    generator: types.ModuleType,
) -> None:
    """Every stem inflection gets an -ise correction and an -ize identity."""
    rendered = generator.render_config()
    for stem in generator.STEMS:
        for ise, ize in generator.SUFFIX_PAIRS:
            assert f'{stem}{ise} = "{stem}{ize}"' in rendered
            assert f'{stem}{ize} = "{stem}{ize}"' in rendered


def test_render_config_accepts_extra_words_verbatim(
    generator: types.ModuleType,
) -> None:
    """Every extra accepted word gets an identity entry."""
    rendered = generator.render_config()
    for word in generator.EXTRA_ACCEPTED_WORDS:
        assert f'{word} = "{word}"' in rendered


def test_render_config_ends_with_trailing_newline(
    generator: types.ModuleType,
) -> None:
    """The rendered document ends with exactly one trailing newline."""
    rendered = generator.render_config()
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")


def test_main_writes_rendered_config_to_explicit_path(
    generator: types.ModuleType,
    tmp_path: pathlib.Path,
) -> None:
    """main() writes the rendered configuration to the given output path."""
    output = tmp_path / "typos.toml"
    generator.main(output)
    assert output.read_text(encoding="utf-8") == generator.render_config()


def test_main_default_path_resolves_to_repository_root(
    generator: types.ModuleType,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() defaults to typos.toml two levels above the script file."""
    fake_script = tmp_path / "scripts" / "generate_typos_config.py"
    monkeypatch.setattr(generator, "__file__", str(fake_script))
    generator.main()
    written = tmp_path / "typos.toml"
    assert written.read_text(encoding="utf-8") == generator.render_config()


def test_committed_config_matches_generator_output(
    generator: types.ModuleType,
) -> None:
    """The committed typos.toml must not drift from the generator."""
    committed = (REPOSITORY_ROOT / "typos.toml").read_text(encoding="utf-8")
    assert committed == generator.render_config()
