"""Briefing presentation contracts."""

from __future__ import annotations

from typing import Protocol, Sequence

from app.domain.models import BriefingFailure, BriefingItem, InvestmentBriefing


class BriefingRenderer(Protocol):
    def render(
        self,
        briefing: InvestmentBriefing,
        items: Sequence[BriefingItem],
        failures: Sequence[BriefingFailure],
    ) -> str:
        ...

