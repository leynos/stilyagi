# 1. Overview of `uv` and `pyproject.toml`

Astral's `uv` is a Rust-based project and package manager that uses
`pyproject.toml` as its central configuration file. Commands such as
`uv init`, `uv sync`, or `uv run` prompt `uv` to:

1. Look for a `pyproject.toml` in the project root and keep a lockfile
   (`uv.lock`) in sync with it.
2. Create a virtual environment (`.venv`) if one does not already exist.
3. Read dependency specifications (and any build-system directives) to install
   or update packages accordingly. (Astral Docs[^1], RidgeRun.ai[^2])

In other words, `pyproject.toml` drives everything, from metadata to
dependencies to build instructions, without needing `requirements.txt` or a
separate `setup.py` file. (Level Up Coding[^3], Python Packaging[^4])

______________________________________________________________________

## 2. The `[project]` table (Python Enhancement Proposal (PEP) 621)

The `[project]` table is defined by PEP 621 and is now the canonical place to
declare metadata (name, version, authors, etc.) and runtime dependencies. At
minimum, PEP 621 requires:

- `name`
- `version`

However, most projects benefit from including at least the following
additional fields for clarity and compatibility:

```toml
[project]
name = "my_project"            # Project name (PEP 621 requirement)
version = "0.1.0"              # Initial semantic version
description = "A brief overview"       # Short summary
readme = "README.md"           # Path to the README file (automatically included)
requires-python = ">=3.14"     # Restrict Python versions, if needed
license = { text = "MIT" }     # Software Package Data Exchange (SPDX)-compatible license expression or file
authors = [
  { name = "Alice Example", email = "alice@example.org" }
]
keywords = ["uv", "astral", "example"]   # (Optional) for metadata registries
classifiers = [
  "Programming Language :: Python :: 3",
  "License :: OSI Approved :: MIT License",
  "Operating System :: OS Independent"
]
dependencies = [
  "requests>=2.25",            # Runtime dependency
  "numpy>=1.23"
]
```

- **`name` and `version`:** Mandatory per PEP 621. (Python Packaging[^4],
  Reddit[^5])
- **`description` and `readme`:** Although not mandatory, they help with
  indexing and packaging tools; `readme = "README.md"` tells `uv` (and PyPI) to
  include the README as the long description. (Astral Docs[^1], Python
  Packaging[^4])
- **`requires-python`:** Constrains which Python interpreters a package
  supports (e.g. `>=3.14`). (Python Packaging[^4], Reddit[^5])
- **`license`:** Specify a licence as an SPDX identifier (via
  `license = { text = "ISC" }`) or point to a file (e.g.
  `license = { file = "LICENSE" }`). (Python Packaging[^4], Reddit[^5])
- **`authors`:** A list of tables with `name` and `email`. Many registries
  (e.g., PyPI) pull this for display. (Python Packaging[^4], Reddit[^5])
- **`keywords` and `classifiers`:** These help search engines and package
  indexes. Classifiers must follow the exact trove list defined by PyPA.
  (Python Packaging[^4], Reddit[^5])
- **`dependencies`:** A list of PEP 508-style requirements (e.g.,
  `"requests>=2.25"`). `uv sync` will install exactly those versions, updating
  the lockfile as needed. (Astral Docs[^1], RidgeRun.ai[^2])

______________________________________________________________________

## 3. Optional and Development Dependencies

Modern projects typically distinguish between "production" dependencies (those
needed at runtime) and "development" dependencies (linters, test frameworks,
etc.). In PEP 621, `[project.optional-dependencies]` covers this split:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=7.0",        # Testing framework
  "black",              # Code formatter
  "flake8>=4.0"         # Linter
]
docs = [
  "sphinx>=5.0",        # Documentation builder
  "sphinx-rtd-theme"
]
```

- **`[project.optional-dependencies]`:** Each table key (e.g. `dev`, `docs`)
  defines a published extra. A maintainer can add an extra dependency via
  `uv add --optional dev pytest` and install that extra with
  `uv sync --extra dev`. (Python Packaging[^4], DevsJC[^6])
- **Why use extras?** The lockfile remains deterministic (via `uv.lock`) while
  still separating concerns (test-only vs. production), and the published
  package exposes those optional features clearly. (Medium[^7], DevsJC[^6])

______________________________________________________________________

## 4. Entry Points and Scripts

Projects that expose command-line interfaces (CLIs) or graphical user
interfaces (GUIs) through a package can use the `[project.scripts]` and
`[project.gui-scripts]` tables provided by PEP 621:

```toml
[project.scripts]
mycli = "my_project.cli:main"    

[project.gui-scripts]
mygui = "my_project.gui:start"
```

- **`[project.scripts]`:** Defines console scripts. Running `uv run mycli`
  prompts `uv` to invoke the `main` function in `my_project/cli.py`.
  (Astral Docs[^8])
- **`[project.gui-scripts]`:** On Windows, `uv` will wrap these in a GUI
  executable; on Unix-like systems, they behave like normal console scripts.
  (Astral Docs[^8])
- **Plugin Entry Points:** Projects that support plugins can use
  `[project.entry-points.'group.name']` to register them. (Astral Docs[^8])

______________________________________________________________________

## 5. Declaring a Build System

PEP 517/518 require a `[build-system]` table to tell tools how to build and
install a project. A "modern" convention is to specify `setuptools>=61.0`
(for editable installs without `setup.py`) or a lighter alternative like
`flit_core`. Below is the typical setup using setuptools:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

- **`requires`:** A list of packages needed at build time. For editable installs
  in `uv`, at least `setuptools>=61.0` and `wheel` are required. (Python
  Packaging[^4], Astral Docs[^8])
- **`build-backend`:** The entry point for the build backend.
  `setuptools.build_meta` is the PEP 517-compliant backend for setuptools.
  (Python Packaging[^4], Astral Docs[^8])
- **Note:** If `[build-system]` is omitted, `uv` will assume
  `setuptools.build_meta:__legacy__` and still install dependencies, but it
  won't editably install the local project unless `tool.uv.package = true` is
  set (see next section). (Astral Docs[^8])

______________________________________________________________________

## 6. `uv`-Specific Configuration (`[tool.uv]`)

Astral `uv` allows projects to inject tool-specific settings in `[tool.uv]`.
The most common option is:

```toml
[tool.uv]
package = true
```

- **`tool.uv.package = true`:** Forces `uv` to build and install the local
  project into its virtual environment every time `uv sync` or `uv run`
  executes. Without this, `uv` only installs dependencies (not the local
  package) if
  `[build-system]` is missing. (Astral Docs[^8])
- Other `uv`-specific keys (e.g., custom indexes, resolver policies) may also
  be set under `[tool.uv]`, but `package` is the most common. (Python
  Packaging[^4], Astral Docs[^8])

______________________________________________________________________

## 7. Putting It All Together: Example `pyproject.toml`

Below is a complete example that demonstrates all sections. Adjust values as
needed for the project at hand.

```toml
[project]
name = "my_project"
version = "0.1.0"
description = "An illustrative example for Astral uv"
readme = "README.md"
requires-python = ">=3.14"
license = { text = "MIT" }
authors = [
  { name = "Alice Example", email = "alice@example.org" }
]
keywords = ["astral", "uv", "pyproject", "example"]
classifiers = [
  "Programming Language :: Python :: 3",
  "License :: OSI Approved :: MIT License",
  "Operating System :: OS Independent"
]
dependencies = [
  "requests>=2.25",
  "numpy>=1.23"
]

[project.optional-dependencies]
dev = [
  "pytest>=7.0",
  "black",
  "flake8>=4.0"
]
docs = [
  "sphinx>=5.0",
  "sphinx-rtd-theme"
]

[project.scripts]
mycli = "my_project.cli:main"

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.uv]
package = true
```

**Explanation of key points:**

1. **Metadata under `[project]`:**

- `name`, `version` (mandatory per PEP 621) (Python Packaging[^4], Reddit[^5])
- `description`, `readme`, `requires-python`: provide clarity about the
  project and help tools like PyPI. (Python Packaging[^4], Reddit[^5])
- `license`, `authors`, `keywords`, `classifiers`: standardized metadata,
  which improves discoverability. (Python Packaging[^4], Reddit[^5])
- `dependencies`: runtime requirements, expressed in PEP 508 syntax.
  (Astral Docs[^1], RidgeRun.ai[^2])

1. **Optional Dependencies (`[project.optional-dependencies]`):**

- Grouped as `dev` (for testing + linting) and `docs` (for documentation).
  These keys are published as extras. Installation is as simple as
  `uv add --optional dev pytest` or `uv sync --extra dev`. (Python
  Packaging[^4], DevsJC[^6])

1. **Entry Points (`[project.scripts]`):**

- Defines a console command `mycli` that maps to `my_project/cli.py:main`.
  Invoking `uv run mycli` will run the `main()` function. (Astral Docs[^8])

1. **Build system:**

- `setuptools>=61.0` plus `wheel` ensures both legacy and editable installs
  work. ✱ Newer versions of setuptools support PEP 660 editable installs
  without a `setup.py` stub. (Python Packaging[^4], Astral Docs[^8])
- `build-backend = "setuptools.build_meta"` tells `uv` how to compile the
  package. (Python Packaging[^4], Astral Docs[^8])

1. **`[tool.uv]`:**

- `package = true` ensures that `uv sync` builds and installs the local
  project (in editable mode) every time dependencies change. Otherwise, `uv`
  treats the project as a collection of scripts only (no package).
  (Astral Docs[^8])

______________________________________________________________________

## 8. Additional Tips & Best Practices

1. **Keep `pyproject.toml` Human-Readable:** Edit it by hand when possible.
   Modern editors (VS Code, PyCharm) offer TOML syntax highlighting and PEP 621
   autocompletion. (Python Packaging[^4])

2. **Lockfile Discipline:** After modifying `dependencies` or any `[project]`
   fields, always run `uv sync` (or `uv lock`) to update `uv.lock`. This
   guarantees reproducible environments. (Astral Docs[^1])

3. **Semantic Versioning:** Follow [semver](https://semver.org/) for `version`
   values (e.g., `1.2.3`). Bump patch versions for bug fixes, minor for
   backward-compatible changes, and major for breaking changes. (Python
   Packaging[^4])

4. **Keep Build Constraints Minimal:** Projects that do not need editable
   installs can omit `[build-system]` (but then `uv` will not build the local
   package; it will only install dependencies). To override, set
   `tool.uv.package = true`. (Astral Docs[^8])

5. **Use Exact or Bounded Ranges for Dependencies:** Rather than `requests`, use
   `requests>=2.25, <3.0` to avoid unexpected major bumps. (DevsJC[^6])

6. **Consider Dynamic Fields Sparingly:** Fields such as
   `dynamic = ["version"]` can be declared when version information is
   computed at build time (e.g. via `setuptools_scm`). When this approach is
   used, ensure the build backend supports dynamic metadata. (Python
   Packaging[^4])

______________________________________________________________________

## 9. Summary

A "modern" `pyproject.toml` for an Astral `uv` project should:

- Use the PEP 621 `[project]` table for metadata and `dependencies`.
- Distinguish optional dependencies under `[project.optional-dependencies]`.
- Define any CLI or GUI entry points under `[project.scripts]` or
  `[project.gui-scripts]`.
- Declare a PEP 517 `[build-system]` (e.g. `setuptools>=61.0`, `wheel`,
  `setuptools.build_meta`) to support editable installs, or omit it and rely on
  `tool.uv.package = true`.
- Include a `[tool.uv]` section, at minimum `package = true` when `uv` should
  build and install the local package.

Following these conventions ensures that a project is fully PEP-compliant,
easy to maintain, and integrates seamlessly with Astral `uv`.

[^1]: [Working on projects | uv - Astral Docs](https://docs.astral.sh/uv/guides/projects/)
[^2]: [UV Tutorial: A Fast Python Package and Project Manager](https://www.ridgerun.ai/post/uv-tutorial-a-fast-python-package-and-project-manager)
[^3]: [Modern Python Development with pyproject.toml and UV](https://levelup.gitconnected.com/modern-python-development-with-pyproject-toml-and-uv-405dfb8b6ec8)
[^4]: [Writing your pyproject.toml – Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
[^5]: [Anyone used UV package manager in production? (Reddit)](https://www.reddit.com/r/Python/comments/1ixryec/anyone_used_uv_package_manager_in_production/)
[^6]: [The Complete Guide to pyproject.toml – devsjc blogs](https://devsjc.github.io/blog/20240627-the-complete-guide-to-pyproject-toml/)
[^7]: [Start Using UV Python Package Manager for Better Dependency Management](https://medium.com/%40gnetkov/start-using-uv-python-package-manager-for-better-dependency-management-183e7e428760)
[^8]: [Configuring projects | uv - Astral Docs](https://docs.astral.sh/uv/concepts/projects/config/)
