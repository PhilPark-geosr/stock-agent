from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agent import _parse_analysis_result
from app.schemas import MarketDataSnapshot, MarketIndicators


def test_parse_analysis_result_accepts_condition_objects_from_model():
    market_data = MarketDataSnapshot(
        symbol="005930.KS",
        data_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        indicators=MarketIndicators(latest_close=70000),
    )
    raw_json = json.dumps(
        {
            "symbol": "WRONG",
            "analysis_time": "2026-06-01T01:00:00+00:00",
            "data_time": "2026-06-01T00:00:00+00:00",
            "verdict": "neutral",
            "summary": "steady",
            "key_reasons": [],
            "risk_factors": [],
            "indicators": {},
            "alert_triggered": True,
            "matched_alert_conditions": [
                {
                    "id": "price_move_abs_gte_3_percent",
                    "kind": "system",
                    "name": "Price move",
                },
                "custom.1",
            ],
            "alert_reason": "condition matched",
        }
    )

    result = _parse_analysis_result(raw_json, market_data)

    assert result.symbol == "005930.KS"
    assert result.data_time == market_data.data_time
    assert result.matched_alert_conditions == [
        "price_move_abs_gte_3_percent",
        "custom.1",
    ]
