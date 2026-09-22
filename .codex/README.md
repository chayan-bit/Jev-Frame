# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The current objective is to complete JF-21 / GitHub #22 and then begin final delivery verification in JF-22 / GitHub #23.
- JF-20 is pushed as `8373949`, its completion evidence was posted, GitHub #21 is closed, and roadmap #1 is checked accurately through JF-20.
- The live prerequisite for JF-21 is closed.
- `src/jev_frame/calibration.py` adds validation-only host selection, frozen proposed policy artifacts, held-out compatibility checks, pending evaluator corrections, and side-effect-free shadow comparison.
- `src/jev_frame/__init__.py` exports the public calibration contracts, and `tests/test_calibration.py` owns the synthetic behavioral checks.
- Held-out evaluation rejects changed policy, manifest, model, judgment, retrieval, or dataset identity and never calls the validation selector.
- Shadow results keep unobserved counterfactual outcomes unknown, preserve unknown usage, and reject every tool dispatch before the original mutation callable can run.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 140 tests.
- The command `uv run --python 3.11 --frozen --all-extras python -m unittest tests.test_calibration -v` passes all five focused checks on CPython 3.11.15.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings across 22 source files.
- No active policy changed, no business tool ran in shadow mode, and no live provider, customer data, online learning, paid evaluation, publication, deployment, or pull request was exercised.
- The remaining action is to inspect and commit JF-21, push it, post completion evidence to GitHub #22, close it if the acceptance criteria remain satisfied, update roadmap #1, and begin JF-22 / GitHub #23.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
