# Jev-Frame documentation

Start with the [project README](../README.md) for installation, the quickstart, and usage guides.

| Document | What it covers |
|---|---|
| [Architecture and contracts](architecture.md) | The design, public contracts, failure and ownership rules, framework integrations, and scope boundaries in depth. |
| [Demo recordings](demos/) | The [VHS](https://github.com/charmbracelet/vhs) tapes behind every GIF in the README and how to re-render them. |
| [Changelog](../CHANGELOG.md) | Release history, generated from Conventional Commits. |
| [Contributing](../CONTRIBUTING.md) | Development setup, checks, commit conventions, demo videos for pull requests, and the release process. |
| [Security policy](../SECURITY.md) | How to report a vulnerability privately and how to handle API keys. |
| [Code of Conduct](../CODE_OF_CONDUCT.md) | Community standards. |

## Demo recordings

Each `.tape` file in [`demos/`](demos/) is a script for [VHS](https://github.com/charmbracelet/vhs).
The files starting with `_` hold the shared look (theme, font, and window size) and the hidden setup that activates the project environment with a neutral `$ ` prompt.
Re-render every demo from the repository root with:

```sh
uv sync --frozen --all-extras
for tape in docs/demos/[!_]*.tape; do vhs "$tape"; done
```

CI renders every tape on each pull request to prove the recordings still run, but it never commits the output.

## Historical records

The original implementation plan and the 0.1.0 verification record are kept at the [`v0.1.0` tag](https://github.com/chayan-bit/Jev-Frame/tree/v0.1.0/docs).
The code, the README, and the architecture guide are authoritative where they differ.
