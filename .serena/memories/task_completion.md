# Task Completion

Backend change:

1. Run the narrowest affected tests during iteration.
2. Run full suite before handoff: `uv run pytest -q`.
3. Current verified baseline (2026-07-24): 34 passed; two dependency deprecation warnings from FastAPI/Starlette HTTPX compatibility and LangGraph serialization defaults.
4. No formatter, linter, or type checker is currently configured; do not claim those checks ran.
5. Review `git diff` and `git status --short`; preserve unrelated user changes.
6. Confirm feature changes include/update a brief design document under `design/` per project guidance.

Desktop change:

1. From `desktop-demo`, run `npm run check`.
2. For integration-affecting changes, start with `npm start` and verify backend health/API interaction.
3. If backend code also changed, complete the backend test steps above.