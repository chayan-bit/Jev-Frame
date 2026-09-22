# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The current objective is to complete JF-18 / GitHub #19 before continuing to the other independent unblocked branch, JF-19 / GitHub #20.
- JF-17 is committed locally as `9ff2c6d`, its completion evidence was posted, and GitHub #18 is closed.
- The live issue confirms that JF-18 depends only on closed JF-08 / #9 and JF-11 / #12.
- `src/jev_frame/documents.py` adds injected bounded page retrieval, immutable passage identities, exact source validation, direct claim decisions, explicit conflicts, and separate retrieval coverage.
- `src/jev_frame/__init__.py` exports the public collection contracts, and `tests/test_documents.py` owns the synthetic behavioral checks.
- Complete multi-page retrieval preserves Unicode spans, duplicate passage identities, and opposing sources, while truncated coverage and stale versions remain unresolved without fabricated certainty.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 126 tests.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings across 19 source files.
- No live provider, external retrieval service, parser, crawler, vector database, publication, deployment, push, or pull request was exercised.
- The remaining action is to inspect and commit JF-18, post the authorized completion evidence to GitHub #19, close it if the acceptance criteria remain satisfied, and begin JF-19.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
