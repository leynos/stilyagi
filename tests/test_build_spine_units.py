"""Unit tests for the mixed-package build spine."""

import collections.abc as cabc
import pathlib
import re
import typing as typ

import pytest
from stilyagi import model, smoke
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context as check

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_SMOKE_REGION = model.Region(kind="heading", text="Stilyagi smoke")
type ExtractDocument = cabc.Callable[[str, model.Syntax], model.Document]


def _collect_recipe_lines(lines: list[str], start: int) -> tuple[str, ...]:
    """Return the tab-indented recipe lines immediately following position *start*."""
    recipe: list[str] = []
    for recipe_line in lines[start + 1 :]:
        if recipe_line.startswith("\t"):
            recipe.append(recipe_line.strip())
            continue
        if recipe_line:
            break
    return tuple(recipe)


def _make_target(makefile: str, target: str) -> tuple[str, tuple[str, ...]]:
    """Return a Makefile target header and its recipe lines."""
    lines = makefile.splitlines()
    for line_number, line in enumerate(lines):
        if line.startswith(f"{target}:"):
            return line, _collect_recipe_lines(lines, line_number)
    msg = f"target {target!r} not found"
    raise AssertionError(msg)


def _normalised_lines(contents: str) -> set[str]:
    """Return stripped non-empty lines for structure-oriented file assertions."""
    return {line.strip() for line in contents.splitlines() if line.strip()}


def test_smoke_helper_exercises_the_public_rust_backed_boundary() -> None:
    """Call the same package smoke helper used by Makefile and CI."""
    document = smoke.smoke_installed_package()

    check(document.syntax is model.Syntax.MARKDOWN, "unexpected smoke syntax")
    check(EXPECTED_SMOKE_REGION in document.regions, "smoke region missing")


@pytest.mark.parametrize(
    ("extract_impl", "expected_match"),
    [
        (lambda _source, syntax: model.Document(syntax=syntax), "at least one region"),
        (
            lambda _source, _syntax: model.Document(
                syntax=model.Syntax.PYTHON_DOCSTRING,
                regions=(EXPECTED_SMOKE_REGION,),
            ),
            "unexpected syntax",
        ),
        (
            lambda _source, _syntax: model.Document(
                syntax=typ.cast("model.Syntax", "markdown"),
                regions=(EXPECTED_SMOKE_REGION,),
            ),
            "malformed syntax",
        ),
        (
            lambda _source, syntax: model.Document(
                syntax=syntax,
                regions=(model.Region(kind="heading", text="Unexpected smoke"),),
            ),
            "source-backed region",
        ),
        (
            lambda _source, _syntax: (_ for _ in ()).throw(
                RuntimeError("bridge error")
            ),
            "unexpected error",
        ),
        (
            lambda _source, _syntax: typ.cast("model.Document", "not a document"),
            "unexpected type",
        ),
    ],
)
def test_smoke_helper_rejects_invalid_documents(
    extract_impl: ExtractDocument,
    expected_match: str,
) -> None:
    """Reject smoke payloads that do not prove the expected bridge contract."""
    with pytest.raises(smoke.SmokeCheckError, match=expected_match):
        smoke.smoke_installed_package(extract_fn=extract_impl)


def test_smoke_helper_wraps_extractor_failures() -> None:
    """Report extractor failures as SmokeCheckError instances."""

    class BridgeFailureError(RuntimeError):
        """Synthetic extractor failure."""

    def fail_extract_document(
        _source: str,
        _syntax: model.Syntax,
    ) -> model.Document:
        """Raise a synthetic bridge failure."""
        raise BridgeFailureError

    with pytest.raises(smoke.SmokeCheckError, match="unexpected error") as error:
        smoke.smoke_installed_package(extract_fn=fail_extract_document)

    check(isinstance(error.value.__cause__, BridgeFailureError), "bridge cause missing")


def test_smoke_helper_rejects_malformed_extractor_result() -> None:
    """Reject extractor results that are not model documents."""

    def extract_wrong_result(
        _source: str,
        _syntax: model.Syntax,
    ) -> model.Document:
        """Return a malformed extractor result."""
        return typ.cast("model.Document", {"syntax": "markdown"})

    with pytest.raises(smoke.SmokeCheckError, match="unexpected type") as error:
        smoke.smoke_installed_package(extract_fn=extract_wrong_result)

    assert error.value.__cause__ is None, "expected error.value.__cause__ is None"


def test_smoke_helper_accepts_expected_region_after_other_regions() -> None:
    """Accept smoke payloads that include the expected region in any position."""

    def extract_expected_region_after_metadata(
        _source: str,
        syntax: model.Syntax,
    ) -> model.Document:
        """Return the smoke region after another region."""
        return model.Document(
            syntax=syntax,
            regions=(
                model.Region(kind="metadata", text="generated by extractor"),
                EXPECTED_SMOKE_REGION,
            ),
        )

    document = smoke.smoke_installed_package(
        extract_fn=extract_expected_region_after_metadata
    )

    check(document.regions[-1] == EXPECTED_SMOKE_REGION, "smoke region not last")


def test_smoke_main_returns_zero_on_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() returns 0 and produces no stderr when the bridge is healthy."""
    exit_code = smoke.main()
    captured = capsys.readouterr()

    assert exit_code == 0, "expected exit_code == 0"
    assert not captured.err, "expected not captured.err"


def test_smoke_main_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return one and print a prefixed SmokeCheckError message to stderr."""

    def fail_smoke_installed_package() -> None:
        """Raise a synthetic smoke failure."""
        raise smoke.SmokeCheckError("broken")

    monkeypatch.setattr(smoke, "smoke_installed_package", fail_smoke_installed_package)

    exit_code = smoke.main()
    captured = capsys.readouterr()

    assert exit_code == 1, "expected exit_code == 1"
    check(
        captured.err.startswith("Stilyagi smoke check failed: "), "smoke prefix missing"
    )
    assert "broken" in captured.err, "expected 'broken' in captured.err"


@pytest.fixture(scope="module")
def makefile_text() -> str:
    """Return the repository Makefile as text, loaded once per module."""
    return (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")


def test_makefile_build_target_depends_on_venv_and_runs_smoke(
    makefile_text: str,
) -> None:
    """Build must declare a .venv dependency and delegate to the smoke target."""
    header, recipe = _make_target(makefile_text, "build")
    assert ".venv" in header, "expected '.venv' in header"
    assert "$(MAKE) smoke" in recipe, "expected '$(MAKE) smoke' in recipe"


def test_makefile_venv_target_declares_manifests_and_sync_recipe(
    makefile_text: str,
    snapshot: SnapshotAssertion,
) -> None:
    """The .venv target must list all workspace manifests and run uv sync."""
    header, recipe = _make_target(makefile_text, ".venv")
    target_contract = {"header": header, "recipe": recipe}
    check(
        target_contract == snapshot(extension_class=JSONSnapshotExtension),
        "expected the .venv target contract to match its revi...",
    )


def test_makefile_smoke_target_invokes_stilyagi_smoke_via_venv(
    makefile_text: str,
) -> None:
    """Smoke must depend on .venv and run stilyagi.smoke through the venv Python."""
    header, recipe = _make_target(makefile_text, "smoke")
    assert ".venv" in header, "expected '.venv' in header"
    check(
        any("VENV_PYTHON" in line for line in recipe),
        "expected any(('VENV_PYTHON' in line for line in reci...",
    )
    check(
        any("VENV_PYTHON" in line and "-m stilyagi.smoke" in line for line in recipe),
        "expected any(('VENV_PYTHON' in line and '-m stilyagi...",
    )


def test_makefile_smoke_release_target_uses_isolated_venv_and_temp_directory(
    makefile_text: str,
) -> None:
    """smoke-release must isolate the wheel install and avoid hard-coding /tmp."""
    header, recipe = _make_target(makefile_text, "smoke-release")
    assert "release-artifact" in header, "expected 'release-artifact' in header"
    assert ".venv" in header, "expected '.venv' in header"
    check(
        any(re.search(r"-m\s+venv\b", line) for line in recipe),
        "expected any((re.search('-m\\\\s+venv\\\\b', line) for l...",
    )
    check(
        any(re.search(r'python"?\s+-m\s+stilyagi\.smoke', line) for line in recipe),
        "expected any((re.search('python\"?\\\\s+-m\\\\s+stilyagi\\...",
    )
    check(
        any(re.search(r"tempfile\.gettempdir\(\)", line) for line in recipe),
        "expected any((re.search('tempfile\\\\.gettempdir\\\\(\\\\)...",
    )
    check(
        any(re.search(r'cd\s+"?\$\$release_tmp"?', line) for line in recipe),
        'expected any((re.search(\'cd\\\\s+"?\\\\$\\\\$release_tmp"?...',
    )
    check(
        all(not re.search(r"cd\s+/tmp\b", line) for line in recipe),
        "expected all((not re.search('cd\\\\s+/tmp\\\\b', line) f...",
    )


def test_makefile_markdownlint_target_excludes_release_smoke_venv(
    makefile_text: str,
) -> None:
    """Markdownlint must depend on tools-docs and exclude generated trees.

    The Markdown file list is shared through the ``MD_FILES_FIND`` variable, so
    the exclusions are asserted on its single definition rather than on each
    recipe line.
    """
    header, recipe = _make_target(makefile_text, "markdownlint")
    assert "tools-docs" in header, "expected 'tools-docs' in header"
    check(
        any("$(MD_FILES_FIND)" in line for line in recipe),
        "expected any(('$(MD_FILES_FIND)' in line for line in...",
    )
    md_find_definitions = [
        line for line in makefile_text.splitlines() if line.startswith("MD_FILES_FIND")
    ]
    assert len(md_find_definitions) == 1, "expected len(md_find_definitions) == 1"
    for excluded in (
        "./.venv-release-smoke/*",
        "./.venv/*",
        "./.uv-cache/*",
        "./.uv-tools/*",
        "./target/*",
        "./crates/stilyagi-pyext/target/*",
    ):
        check(
            f"-not -path '{excluded}'" in md_find_definitions[0],
            "expected f\"-not -path '<excluded>'\" in md_find_defin...",
        )


def test_makefile_markdownlint_target_enforces_spelling(
    makefile_text: str,
) -> None:
    """Markdownlint must depend on the complete spelling gate.

    The spelling gate must go through the pinned ``$(TYPOS)`` command with the
    repository configuration and ``--force-exclude`` so the ``typos.toml``
    excludes hold even for explicitly passed paths.
    """
    markdown_header, _markdown_recipe = _make_target(makefile_text, "markdownlint")
    assert "spelling" in markdown_header, "expected 'spelling' in markdown_header"
    _spelling_header, spelling_recipe = _make_target(makefile_text, "spelling")
    typos_lines = [line for line in spelling_recipe if "$(TYPOS)" in line]
    assert len(typos_lines) == 1, "expected len(typos_lines) == 1"
    check("$(MD_FILES_FIND)" in typos_lines[0], "Markdown list missing")
    check("--config typos.toml" in typos_lines[0], "typos config missing")
    check("--force-exclude" in typos_lines[0], "force exclusion missing")
    assert typos_lines[0].endswith(" --"), "expected typos_lines[0].endswith(' --')"
    config_header, config_recipe = _make_target(makefile_text, "spelling-config")
    check("spelling-helper-test" in config_header, "helper gate missing")
    check(
        config_recipe == ("$(TYPOS_CONFIG_BUILDER) --repository . --check",),
        "expected config_recipe == ('$(TYPOS_CONFIG_BUILDER) ...",
    )
    check(
        re.search(
            r"^TYPOS_CONFIG_BUILDER_COMMIT\s*:=\s*[0-9a-f]{40}\s*$",
            makefile_text,
            re.MULTILINE,
        ),
        "expected re.search('^TYPOS_CONFIG_BUILDER_COMMIT\\\\s*...",
    )
    check(
        re.search(
            r"^TYPOS_VERSION\s*\?=\s*\d+\.\d+\.\d+\s*$", makefile_text, re.MULTILINE
        ),
        "expected re.search('^TYPOS_VERSION\\\\s*\\\\?=\\\\s*\\\\d+\\\\...",
    )


def test_makefile_lint_tools_resolve_through_uv(makefile_text: str) -> None:
    """Lint helper tools must resolve through uv-managed commands."""
    check(
        re.search(
            r"^INTERROGATE\s*\?=\s*\$\(UV_RUN\)\s*interrogate\s*$",
            makefile_text,
            re.MULTILINE,
        ),
        "INTERROGATE no longer resolves through $(UV_RUN)",
    )
    check(
        re.search(
            r"^TYPOS\s*=\s*env\s+\$\(UV_ENV\)\s+\$\(UV\)\s+tool\s+run\s+"
            r"typos@\$\(TYPOS_VERSION\)\s*$",
            makefile_text,
            re.MULTILINE,
        ),
        "TYPOS no longer resolves through the pinned uv tool command",
    )


def test_makefile_nixie_target_uses_shared_markdown_file_list(
    makefile_text: str,
) -> None:
    """Nixie must depend on tools-docs and validate the shared Markdown list."""
    header, recipe = _make_target(makefile_text, "nixie")
    assert "tools-docs" in header, "nixie no longer depends on tools-docs"
    nixie_lines = [line for line in recipe if "$(NIXIE)" in line]
    assert len(nixie_lines) == 1, "nixie target no longer has one NIXIE command"
    check("$(MD_FILES_FIND)" in nixie_lines[0], "Markdown list missing")
    assert "--no-sandbox" in nixie_lines[0], "nixie no longer runs without sandboxing"


def test_makefile_tools_docs_target_checks_documentation_tools(
    makefile_text: str,
) -> None:
    """tools-docs must verify markdownlint, nixie, and uv are installed."""
    _header, recipe = _make_target(makefile_text, "tools-docs")
    for tool in ("$(MDLINT)", "$(NIXIE)", "uv"):
        check(
            any(f"ensure_tool,{tool}" in line for line in recipe),
            f"tools-docs no longer checks {tool}",
        )
