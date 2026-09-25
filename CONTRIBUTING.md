# Contributing to Jev-Frame

Thanks for your interest in improving Jev-Frame.
Bug reports, documentation fixes, and focused pull requests are all welcome.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer, then create the locked environment:

```sh
git clone https://github.com/chayan-bit/Jev-Frame.git
cd Jev-Frame
uv sync --frozen --all-extras
```

## Tests

The suite is fully offline and uses scripted provider doubles, so it never needs a TypeSafe API key:

```sh
uv run --frozen --all-extras python -m unittest discover -s tests -v
```

Add or update tests for every behavior change, and keep new tests offline and deterministic.

## Lint and type checks

```sh
uv run --frozen --all-extras ruff check src tests examples
uv run --frozen --all-extras mypy src
```

If you change dependencies, update `pyproject.toml` and regenerate the lockfile with `uv lock`.

## Pull requests

- Open an issue first for large or API-changing work so the design can be discussed.
- Keep each pull request focused on one change and describe what changed and why.
- Include a short test plan listing the commands you ran.
- Make sure CI passes on all supported Python versions.
- Use [Conventional Commits](https://www.conventionalcommits.org/) messages such as `fix: reject stale evidence before dispatch`.
- Never commit API keys, `.env` files, captured live payloads, or other private data.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
