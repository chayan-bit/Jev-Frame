# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The current objective is to complete JF-19 / GitHub #20 and then begin the newly unblocked JF-20 / GitHub #21.
- The verified JF-17 and JF-18 commits were pushed to `origin/codex/jev-frame-implementation`, their completion evidence was posted, and GitHub #18 and #19 are closed.
- The live issue confirms that JF-19 depends only on closed JF-09 / #10.
- `src/jev_frame/fixtures.py` adds explicit capture allowlists, versioned source and call manifests, deterministic provider and tool doubles, material-gap refusal, finding diffs, and separately configured reevaluation.
- `src/jev_frame/__init__.py` exports the public fixture contracts, and `tests/test_fixtures.py` owns the synthetic behavioral checks.
- Capture does not accept arbitrary runtime state or exceptions, evaluator labels are structurally separate, and offline replay has no live provider or original-tool fallback.
- The first focused run exposed incorrect test construction for `CompiledQuestion` and `Tool` bindings; those test defects were corrected without changing the implementation contract.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 131 tests.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings across 20 source files.
- No live provider, original business mutation, durable resume, production trace export, paid evaluation, publication, deployment, or pull request was exercised.
- The remaining action is to inspect and commit JF-19, push it, post completion evidence to GitHub #20, close it if the acceptance criteria remain satisfied, update roadmap #1, and begin JF-20 / GitHub #21.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
