# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The current objective is to complete JF-20 / GitHub #21 and then begin JF-21 / GitHub #22.
- JF-19 is pushed as `3df5e33`, its completion evidence was posted, GitHub #20 is closed, and roadmap #1 is checked accurately through JF-19.
- All live prerequisites for JF-20 are closed.
- `src/jev_frame/evaluation.py` adds evaluator-isolated case records, split and group validation, host-supplied public-operation variants, grouped metrics, shared-ledger accounting, and deterministic report serialization.
- `src/jev_frame/__init__.py` exports the public evaluation contracts, and `tests/test_evaluation.py` owns the synthetic behavioral checks.
- A real `DecisionClient` comparison confirms evaluator sentinels stay out of provider state, related variants count as one independent group, and missing foreign host usage remains partial rather than zero.
- Callback exceptions retain only a service-failure category, while harmful automatic errors, unnecessary handoffs, retrieval failures, correct escalation, zero denominators, unknown cost, versions, seeds, and capability combinations remain visible.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 135 tests.
- The command `uv run --python 3.11 --frozen --all-extras python -m unittest tests.test_evaluation -v` passes all four focused checks on CPython 3.11.15.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings across 21 source files.
- No paid benchmark, live provider, consequential effect, private dataset, automatic policy promotion, publication, deployment, or pull request was exercised.
- The remaining action is to inspect and commit JF-20, push it, post completion evidence to GitHub #21, close it if the acceptance criteria remain satisfied, update roadmap #1, and begin JF-21 / GitHub #22.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
