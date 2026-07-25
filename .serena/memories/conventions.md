# Conventions

- Preserve layered boundaries documented in `docs/backend_architecture_notes.md`: routes handle HTTP and delegate; services express use cases against Protocols; adapters live under repositories/integrations/tools; concrete wiring stays in core/api dependency modules.
- Use dependency inversion for external services and persistence. Add or extend contracts in `app/interfaces` rather than importing concrete implementations into services.
- API request/response and agent data contracts belong in `app/schemas`; domain helpers/concepts belong in `app/domain`.
- Maintain type hints and explicit Protocol-based dependencies; dependencies are constructor-injected into `AnalysisService` for testability.
- Keep symbols focused. Known large aggregation files (`services.py`, `repositories.py`, `schemas.py`) should not accumulate unrelated responsibilities.
- Project design rule from `Agent.md`: feature work requires a brief, implementation-agnostic design document under `design/`; consult `design_draft.md`; critically evaluate proposed designs.
- Prefer Serena symbol overview/search/reference tools before reading entire code files. Store only durable facts in memory.
- Tests mirror behavior by area in `tests/test_*.py`; use dependency fakes/fixtures rather than live Gemini, Kakao, or market-network calls.
- Do not commit API keys, Kakao tokens, generated databases, or local environment values.