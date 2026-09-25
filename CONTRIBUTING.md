# Contributing to Jev-Frame

Thanks for your interest in improving Jev-Frame.
Bug reports, documentation fixes, and focused pull requests are all welcome.
Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Search [existing issues](https://github.com/chayan-bit/Jev-Frame/issues) first, and open one for large or API-changing work so the design can be discussed before you write code.
- Ask usage questions in [Discussions](https://github.com/chayan-bit/Jev-Frame/discussions) rather than in issues.
- Report security problems privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer, then create the locked environment:

```sh
git clone https://github.com/chayan-bit/Jev-Frame.git
cd Jev-Frame
uv sync --frozen --all-extras
```

## Checks

Every check below runs in CI on each pull request, and all of them run offline without a TypeSafe API key.

| Check | Command |
|---|---|
| Tests | `uv run --frozen --all-extras python -m unittest discover -s tests -v` |
| Lint | `uv run --frozen --all-extras ruff check src tests examples scripts` |
| Types | `uv run --frozen --all-extras mypy src scripts` |
| README snippets | `uv run --frozen --all-extras python scripts/check_readme.py README.md` |
| Wheel | `uv build`, then install the wheel into a fresh virtual environment and run `examples/quickstart.py` |
| Demo tapes | `for tape in docs/demos/[!_]*.tape; do vhs "$tape"; done` (needs [VHS](https://github.com/charmbracelet/vhs)) |

Add or update tests for every behavior change, and keep new tests offline and deterministic.
The README check executes every code block in `README.md`, so a README example that stops working fails CI.
If you change dependencies, update `pyproject.toml` and regenerate the lockfile with `uv lock`.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/), because the changelog and version numbers are generated from them.

| Type | Use it for | Changelog section |
|---|---|---|
| `feat` | A new user-facing capability | Added |
| `fix` | A bug fix | Fixed |
| `perf` | A performance improvement | Performance |
| `refactor` | A behavior-preserving code change | Changed |
| `revert` | Reverting an earlier commit | Reverted |
| `deps` | A dependency update | Dependencies |
| `docs`, `test`, `ci`, `build`, `style`, `chore` | Everything else | Not listed |

Mark breaking changes with `!` after the type (for example `feat!: rename DecisionInputs.id`) or a `BREAKING CHANGE:` footer.
Examples: `fix(runtime): reject stale evidence before dispatch` and `docs: explain no-fit selection`.

## Pull requests

- Keep each pull request focused on one change and explain what changed and why.
- **Include a demo video.** Every pull request description must embed a short recording (GIF or MP4) of what the change does, for example the new behavior running, the examples, or the checks passing.
  Record it with [VHS](https://github.com/charmbracelet/vhs) using the shared look in `docs/demos/_settings.tape`, or any screen recorder, and drag the file into the pull request description.
  Changes that affect a README demo should also update its tape in `docs/demos/` and re-render the GIF.
- Fill in the test plan in the pull request template with the commands you ran.
- Make sure CI passes; `main` only accepts changes whose required checks are green.
- Never commit API keys, `.env` files, captured live payloads, personal paths, or other private data.

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please).

1. Every push to `main` updates an open release pull request titled like `chore(main): release 0.2.0`.
   It bumps the version in `pyproject.toml`, `uv.lock`, and the README install commands, and adds a `CHANGELOG.md` section built from the Conventional Commits since the last release.
2. The release workflow dispatches CI on the release pull request branch each time it opens or updates the pull request, so the required checks run without any manual step.
   Do not close and reopen the release pull request, because that races with release-please and can strip its `autorelease: pending` label.
3. When the maintainer merges it, release-please tags the merge commit (for example `v0.2.0`) and publishes a GitHub release with the same notes.

Never edit `CHANGELOG.md` by hand.
The history up to `v0.1.0` was generated with [git-cliff](https://git-cliff.org/) (`git cliff --latest -o CHANGELOG.md`, configured in `cliff.toml`), and release-please appends every later release in the same format.
Jev-Frame is not published to PyPI yet, so users install releases from their Git tags.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
