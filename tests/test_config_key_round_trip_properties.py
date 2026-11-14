"""Property coverage for config-key rendering and parsing.

`config` prints each origin as a TOML dotted key and accepts that spelling back
as an argument, so the two functions form a round trip: whatever the renderer
produces, the parser must read back as the same components. The example tests in
`test_config_inspection_dotted_keys.py` pin one glob and one astral character.
They cannot show the invariant holds across the combinations that actually
break quoting -- a component containing a quote, a backslash, a dot, or nothing
at all.

The properties are stated over arbitrary components rather than arbitrary
*valid* ones because the renderer's whole job is to make any string survive the
trip. A generator restricted to bare keys would only exercise the branch that
needs no quoting, and would keep passing if the quoting branch broke.

Run these with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_config_key_round_trip_properties.py
"""

import tomllib

from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi import cli_config_command

# Characters that a naive renderer would let through unescaped and that TOML
# then reads differently: the quote that would end the component, the
# backslash that escapes the next character, and the dot that splits a key.
_HOSTILE_COMPONENTS = st.text(
    alphabet=st.sampled_from(['"', "'", "\\", ".", "a", "Z", "0", "-", "_", "\n"]),
    min_size=0,
    max_size=6,
)

# Bare keys exercise the branch that must *not* quote; the rest exercise the
# branch that must. Empty strings are included because they cannot be bare
# keys and have no obvious quoting either.
_KEY_COMPONENTS = st.one_of(
    st.from_regex(r"[A-Za-z0-9_-]{1,8}", fullmatch=True),
    _HOSTILE_COMPONENTS,
)

_PATHS = st.lists(_KEY_COMPONENTS, min_size=1, max_size=4).map(tuple)


def _rendered(path: tuple[str, ...]) -> str:
    """Render one origin path the way the command prints it."""
    return cli_config_command._spell_origin_path(path)


@settings(max_examples=200, deadline=None)
@given(path=_PATHS)
def test_a_rendered_key_parses_back_to_the_same_components(
    path: tuple[str, ...],
) -> None:
    """Rendering then parsing preserves every component, in order."""
    rendered = _rendered(path)

    assert cli_config_command._parse_origin_path(rendered) == path, (
        f"expected {rendered!r} to parse back to {path!r}"
    )


@settings(max_examples=200, deadline=None)
@given(path=_PATHS)
def test_a_rendered_key_is_toml_that_selects_its_path(
    path: tuple[str, ...],
) -> None:
    """The printed spelling is a TOML key path naming the same location.

    Internal round-tripping is not enough by itself. The spelling is printed
    for a human to paste back, and the configuration file it came from is
    TOML, so the key must also parse in that grammar and address the same
    leaf. A spelling the parser happened to accept but TOML read differently
    would still point a reader at the wrong setting.
    """
    rendered = _rendered(path)

    parsed = tomllib.loads(f"{rendered} = 1")

    selected: object = parsed
    for component in path:
        assert isinstance(selected, dict), (
            f"expected {rendered!r} to nest, reached a leaf before {component!r}"
        )
        assert component in selected, (
            f"expected {rendered!r} to address {component!r}, got {sorted(selected)}"
        )
        selected = selected[component]
    assert selected == 1, f"expected {rendered!r} to select the value at {path!r}"


@settings(max_examples=100, deadline=None)
@given(path=_PATHS)
def test_a_bare_component_is_never_quoted(path: tuple[str, ...]) -> None:
    """Leave components already in bare-key form unquoted."""
    rendered = _rendered(path)

    spellings = cli_config_command._KEY_COMPONENT.findall(rendered)
    assert len(spellings) == len(path), (
        f"expected one spelling per component in {rendered!r}, got {spellings}"
    )
    for component, spelling in zip(path, spellings, strict=True):
        if cli_config_command._BARE_KEY.match(component):
            assert spelling == component, (
                f"expected bare component {component!r} to stay unquoted"
            )


def test_the_example_regression_still_holds() -> None:
    """Keep the dotted-glob case as a named example beside the properties."""
    path = ("lint", "per-file-ignores", "*.md")

    rendered = cli_config_command._spell_origin_path(path)

    assert rendered == 'lint.per-file-ignores."*.md"', (
        "expected the glob component to be quoted rather than flattened"
    )
    assert cli_config_command._parse_origin_path(rendered) == path, (
        "expected the quoted glob to parse back to its original components"
    )
