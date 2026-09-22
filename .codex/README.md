# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The current objective is to complete JF-17 / GitHub #18 and then continue to the next issue whose live prerequisites are closed.
- The branch is `codex/jev-frame-implementation` and the starting commit for JF-17 is `d3d1b9f`.
- The live issue confirms that JF-17 depends only on closed JF-16 / GitHub #17.
- `src/jev_frame/artifacts.py` adds the generic generate-verify recipe, immutable artifact revisions, deterministic checks, semantic judgments, revision-specific findings, completion support, and bounded no-progress behavior.
- `src/jev_frame/__init__.py` exports the public artifact recipe contracts, and `tests/test_artifacts.py` owns the synthetic behavioral checks.
- Required exact failure and error block semantic execution, changed revisions rerun their checks, identical output stops immediately, and completion requires current evidence supporting every declared field.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 123 tests.
- The focused four-test artifact suite also passes in an isolated CPython 3.11 environment with all extras.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings across 18 source files.
- The GitHub MCP loader was unavailable because `github` is missing from its local index, so authenticated `gh` supplied the read-only live issue state.
- No live provider, generated-code execution, consequential effect, publication, deployment, push, or pull request was exercised.
- The remaining action is to inspect and commit the JF-17 diff, post the authorized completion evidence to GitHub #18, close it if the acceptance criteria remain satisfied, and inspect the next live prerequisite set.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
