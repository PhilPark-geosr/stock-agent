# Stock Agent

AI-assisted stock analysis service built with FastAPI. The app fetches market data with `yfinance`, asks Gemini for a structured Korean stock analysis, stores results in SQLite, and exposes both a small web page and JSON API.

## Requirements

- Python 3.11 or newer
- Gemini API key

## Setup

```bash
git clone https://github.com/PhilPark-geosr/stock-agent.git
cd stock-agent

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"

cp .env.example .env
```

Edit `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=sqlite:///./stock_agent.db
```

## Run

```bash
python -m uvicorn app.main:app --reload
```

On this Windows workspace, use the bundled Python directly:

```powershell
.\.python311\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` in your browser.

## API

- `GET /health` - health check
- `GET /watchlist` - list watchlist symbols
- `POST /watchlist` - add a symbol, for example `{"symbol": "005930.KS"}`
- `DELETE /watchlist/{symbol}` - remove a symbol
- `POST /alert-conditions` - validate and save a natural-language custom alert condition
- `GET /alert-conditions` - list saved custom alert conditions
- `DELETE /alert-conditions/{condition_id}` - remove a custom alert condition
- `GET /stocks/{symbol}/analysis/latest` - get the latest analysis, creating one when no cached result exists
- `POST /internal/briefings/run` - generate a pre-market or post-market briefing
- `GET /users/me/briefings` - list the current user's briefings
- `GET /users/me/briefings/{id}` - get a briefing with ranked items and delivery state

Until an authentication provider is connected, user-scoped endpoints read the development
identity from the `X-User-Id` header and default to `default`.

The background scheduler also checks KRX and US exchange sessions. It creates
pre-market briefings during the configured lead window and post-market summaries
after the calendar-confirmed close. Exchange holidays, early closes, and daylight
saving transitions come from `exchange-calendars`. Passing `"force": true` to the
internal run endpoint regenerates the existing daily briefing as a new version.

Security search, `@` mentions, and `#` filter resolution belong to the separate
security-search context (PR #23). The briefing feature stores only the already
resolved scope snapshot and does not parse search text.

## Tests

```bash
pytest
```
