"""Read a wheel's ``METADATA`` into the reviewed snapshot shape.

``tests/test_maturin_build.py`` builds the native wheel and snapshots it, and
``tests/test_maturin_wheel_units.py`` holds the readers to handwritten
documents rather than to whatever maturin happened to emit. Both need the same
three steps: scan the headers, keep only the fields the snapshot reviews, and
read the first value of a repeated header. They live here so the scan has one
home and can be exercised through its fold and end-of-headers rules, which
``parse_metadata`` alone would hide.

A ``METADATA`` body is an RFC 822 style block: ``Key: value`` lines, a
continuation line that starts with a space or tab and belongs to the previous
header, and an empty line that ends the headers. Only the headers are wanted.
"""

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def header_value(headers: dict[str, list[str]], key: str) -> str | None:
    """Return the first parsed metadata header value for key."""
    values = headers.get(key)
    return values[0] if values else None


def parse_headers(lines: cabc.Iterable[str]) -> dict[str, list[str]]:
    """Return every header a metadata document states, in its stated order.

    Returns
    -------
    dict[str, list[str]]
        Each header and the values the scan accumulated for it.
    """
    # The fold and the end-of-headers rule are invisible through
    # ``parse_metadata``, which keeps only the reviewed headers, so they are
    # exercised through this wider scan rather than by repeating it.
    headers: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in lines:
        if line.startswith((" ", "\t")) and current_key is not None:
            headers[current_key][-1] = f"{headers[current_key][-1]} {line.strip()}"
            continue
        if ":" not in line:
            break
        key, value = line.split(":", 1)
        current_key = key.strip()
        headers.setdefault(current_key, []).append(value.strip())
    return headers


def parse_metadata(raw_metadata: str) -> dict[str, object]:
    """Parse wheel METADATA into the reviewed snapshot shape."""
    headers = parse_headers(raw_metadata.splitlines())

    return {
        "name": header_value(headers, "Name"),
        "version": header_value(headers, "Version"),
        "requires_python": header_value(headers, "Requires-Python"),
        "requires_dist": sorted(headers.get("Requires-Dist", [])),
        "classifiers": sorted(headers.get("Classifier", [])),
    }
