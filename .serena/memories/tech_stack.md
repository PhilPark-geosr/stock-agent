# Tech Stack

- Python >=3.11; root dependency/package workflow uses uv (`uv.lock`, PEP 621 `pyproject.toml`, setuptools build backend).
- Backend: FastAPI, Uvicorn, Jinja2, Pydantic 2, SQLAlchemy 2, HTTPX.
- AI/workflow: LangGraph, LangChain Google GenAI; market data: yfinance.
- Persistence default/configurable through `DATABASE_URL`; local SQLite files are used.
- Tests: pytest 8; configuration sets `tests` as test path and project root on Python path.
- No repository linter, formatter, or static type-checker is configured in `pyproject.toml`.
- Desktop module: Electron 42.4.1, Node >=22.12, npm-oriented documented workflow; plain JavaScript without React. See `mem:desktop/core`.
- Runtime configuration comes from environment variables; secrets include Gemini and Kakao credentials and must remain in local `.env`, never source control.