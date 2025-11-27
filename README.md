# stilyagi

`stilyagi` is a Cyclopts-based CLI for packaging and installing Vale styles.
It no longer ships the Concordat style itself; the ruleset now lives in its
own repository.

- Install dependencies with `uv sync --group dev`.
- Run the CLI from a style checkout, for example
  `uv run stilyagi zip --project-root /path/to/concordat-style`.
- See `docs/users-guide.md` for end-to-end packaging and install workflows.
