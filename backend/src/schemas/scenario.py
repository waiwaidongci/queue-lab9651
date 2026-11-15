from typing import Literal
from pydantic import BaseModel, Field


class TicketClassInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=60)
    level: Literal["normal", "urgent"]
    arrival_share: float = Field(gt=0, lt=1.0000001, allow_inf_nan=False)
    mean_service_minutes: float = Field(ge=.001, le=120, allow_inf_nan=False)


class WindowInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=60)
    allowed: list[str] = Field(min_length=1)


class ScenarioInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    profile_id: int
    servers: int = Field(ge=1, le=20)
    mean_service_minutes: float = Field(ge=.001, le=120, allow_inf_nan=False)
    # 多票种抢占路径字段；mode=priority 时必填。
    mode: Literal["fcfs", "priority"] = "fcfs"
    total_arrival_rate: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    ticket_classes: list[TicketClassInput] = Field(default_factory=list)
    windows: list[WindowInput] = Field(default_factory=list)
