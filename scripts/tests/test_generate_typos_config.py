"""Unit tests for the ``typos.toml`` generator script.

The generator is a standalone ``uv run`` script rather than a package
module, so it is loaded here through ``importlib`` from its file path.
"""

import importlib.util
import json
import pathlib
import re
import shutil
import subprocess  # noqa: S404 - runs the pinned, trusted typos binary via uv.
import tempfile
import tomllib
import types
import typing as typ

import pytest
from hypothesis import given
from hypothesis import strategies as st

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "generate_typos_config.py"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SAFE_FILENAME_CHARS = tuple("abcdefghijklmnopqrstuvwxyz0123456789_-")
SAFE_TYPOS_FILENAMES = st.lists(
    st.sampled_from(SAFE_FILENAME_CHARS),
    min_size=1,
    max_size=32,
).map(lambda chars: f"{''.join(chars)}.toml")


@pytest.fixture(name="generator", scope="module")
def generator_fixture() -> types.ModuleType:
    """Load the generator script as a module from its file path."""
    spec = importlib.util.spec_from_file_location("generate_typos_config", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module, types.ModuleType)
    return module


@pytest.fixture(name="rendered_config", scope="module")
def rendered_config_fixture(generator: types.ModuleType) -> str:
    """Render the generator output once for property tests."""
    return typ.cast("str", generator.render_config())


@pytest.fixture(name="committed_config", scope="module")
def committed_config_fixture() -> str:
    """Read the committed typos.toml once for the drift and parse tests."""
    return (REPOSITORY_ROOT / "typos.toml").read_text(encoding="utf-8")


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


def test_render_config_parses_as_valid_toml(
    generator: types.ModuleType,
) -> None:
    """Rendered config is valid TOML with no duplicate extend-words keys."""
    parsed = tomllib.loads(generator.render_config())
    extend_words = parsed["default"]["extend-words"]
    expected = len(generator.EXTRA_ACCEPTED_WORDS) + 2 * len(generator.STEMS) * len(
        generator.SUFFIX_PAIRS
    )
    assert len(extend_words) == expected, (
        f"expected {expected} extend-words entries, got {len(extend_words)}"
    )


@given(data=st.data())
def test_render_config_property_emits_sampled_stem_suffix_pair(
    generator: types.ModuleType,
    rendered_config: str,
    data: st.DataObject,
) -> None:
    """A sampled stem and suffix pair gets correction and identity entries."""
    stem = data.draw(st.sampled_from(generator.STEMS))
    ise, ize = data.draw(st.sampled_from(generator.SUFFIX_PAIRS))

    assert f'{stem}{ise} = "{stem}{ize}"' in rendered_config
    assert f'{stem}{ize} = "{stem}{ize}"' in rendered_config


@given(data=st.data())
def test_render_config_property_accepts_sampled_extra_word(
    generator: types.ModuleType,
    rendered_config: str,
    data: st.DataObject,
) -> None:
    """A sampled extra accepted word gets an identity entry."""
    word = data.draw(st.sampled_from(sorted(generator.EXTRA_ACCEPTED_WORDS)))

    assert f'{word} = "{word}"' in rendered_config


@given(filename=SAFE_TYPOS_FILENAMES)
def test_main_property_writes_rendered_config_without_mutation(
    generator: types.ModuleType,
    filename: str,
) -> None:
    """main() writes rendered content exactly to a sampled safe filename."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        output = pathlib.Path(temporary_directory) / filename
        generator.main(output)

        assert output.read_text(encoding="utf-8") == generator.render_config()


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
    committed_config: str,
) -> None:
    """The committed typos.toml must not drift from the generator."""
    assert committed_config == generator.render_config()


def test_committed_config_parses_as_valid_toml(committed_config: str) -> None:
    """Committed typos.toml is valid TOML with the expected locale and extend-words."""
    parsed = tomllib.loads(committed_config)
    locale = parsed["default"]["locale"]
    assert locale == "en-gb", f'expected locale "en-gb", got {locale!r}'
    assert parsed["default"]["extend-words"], "extend-words table is unexpectedly empty"


def _pinned_typos_version() -> str:
    """Read the pinned typos version from the Makefile single source of truth.

    The Makefile ``markdownlint`` gate runs ``typos`` at ``TYPOS_VERSION``;
    the smoke test resolves the same pin here rather than duplicating it, so
    the end-to-end check always exercises the version the gate enforces.
    """
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TYPOS_VERSION\s*\?=\s*(\S+)", makefile, re.MULTILINE)
    assert match is not None, "TYPOS_VERSION not found in Makefile"
    return match.group(1)


@pytest.mark.slow
@pytest.mark.timeout(120)
def test_generated_config_loads_in_typos(
    generator: types.ModuleType,
    tmp_path: pathlib.Path,
) -> None:
    """The real typos binary loads the config and enforces Oxford spelling.

    ``tomllib`` parsing proves the document is well-formed TOML, but only the
    ``typos`` binary proves the config is one it will actually accept and act
    on. A duplicate key or a rejected setting makes typos exit without the
    expected correction, so this asserts the British ``organise`` is corrected
    to the Oxford ``organize``. Skipped when the pinned binary cannot be run.
    """
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        pytest.skip("uv is unavailable to run the pinned typos binary")

    config = tmp_path / "typos.toml"
    generator.main(config)
    sample = tmp_path / "sample.md"
    sample.write_text("The team will organise the release.\n", encoding="utf-8")

    try:
        result = subprocess.run(  # noqa: S603 - argv is trusted literals and repo paths; no user input.
            [
                uv_executable,
                "tool",
                "run",
                f"typos@{_pinned_typos_version()}",
                "--config",
                str(config),
                "--format",
                "json",
                str(sample),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"could not run the pinned typos binary: {exc}")

    corrections = {
        entry["typo"]: entry.get("corrections", [])
        for line in result.stdout.splitlines()
        if line.strip()
        for entry in (json.loads(line),)
        if entry.get("type") == "typo"
    }
    assert corrections.get("organise") == ["organize"], (
        "generated config did not load or enforce Oxford spelling; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
