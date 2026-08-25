import asyncio
import logging

from app.main import app, lifespan


def test_startup_reports_runtime_user_alert_delivery_as_disabled(monkeypatch, caplog) -> None:
    monkeypatch.setattr("app.main.init_db", lambda: None)

    async def start_and_stop() -> None:
        async with lifespan(app):
            pass

    with caplog.at_level(logging.INFO):
        asyncio.run(start_and_stop())

    assert "Runtime user alert delivery disabled" in caplog.text
    assert "Kakao alerts enabled" not in caplog.text
