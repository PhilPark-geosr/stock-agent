# Project Core

- AI-assisted stock analysis service: FastAPI backend fetches yfinance market data, runs Gemini/LangGraph analysis in Korean, persists SQLite results, and exposes HTML + JSON APIs.
- Backend source root: `app/`; tests: `tests/`; architecture/design records: `design/` and `docs/`.
- Practical layered dependency direction:
  - `app/api` -> `app/services` -> `app/interfaces`
  - `app/application`, `app/repositories`, `app/integrations` implement workflows/adapters behind interfaces.
  - Concrete dependency wiring belongs in `app/core/container.py` and `app/api/deps.py`.
  - Services must not directly depend on FastAPI or concrete DB/LLM/market-data/notification adapters.
- Main runtime entry: `app.main:app`; application factory: `app/main.py:create_app`.
- Main use-case coordinator: `app/services/services.py:AnalysisService`; analysis graph: `app/application/analysis_graph.py:MainAnalysisAgent`; custom rules: `app/application/custom_rule_agent.py`.
- SQLAlchemy repositories are currently grouped in `app/repositories/repositories.py`; ORM models are currently in `app/domain/models.py`.
- Read stack details in `mem:tech_stack`, commands in `mem:suggested_commands`, code/design rules in `mem:conventions`, and done criteria in `mem:task_completion`.
- The Electron client is a separate module; read `mem:desktop/core` before desktop work.