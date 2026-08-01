# Suggested Commands

Run from repository root in PowerShell unless noted.

- Install/sync backend dependencies: `uv sync`
- Run backend in development: `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Windows helper that stops an existing listener on port 8000 then starts the venv server: `.\scripts\dev.ps1`
- Run full backend suite: `uv run pytest`
- Run focused test: `uv run pytest tests\test_api.py -q`
- Inspect working tree: `git status --short`; inspect changes: `git diff`
- If the machine's default uv cache is broken or unwritable, set a temporary cache for the command: `$env:UV_CACHE_DIR = Join-Path $env:TEMP 'stock-agent-uv-cache'`.

Desktop commands from `desktop-demo`:

- Install: `npm install`
- Start Electron client: `npm start`
- Syntax-check all desktop JavaScript: `npm run check`

The Electron client checks `http://127.0.0.1:8000/health` and can start the backend from the root `.venv`; override backend URL with `STOCK_AGENT_API_URL`.