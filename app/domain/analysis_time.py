"""Time meaning captured with a particular analysis input."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChartBasis(BaseModel):
    """A daily session date is a calendar label, not a closing instant."""

    model_config = ConfigDict(frozen=True)

    interval: str
    session_date: date | None = None
    source_timezone: str | None = None
    finality: Literal["unknown"] = "unknown"
