from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..config.database import Base


class TicketClassConfig(Base):
    """多票种配置：到达占比、平均服务时长、普通/紧急等级。"""
    __tablename__ = "ticket_class_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("service_scenarios.id"))
    code: Mapped[str]
    name: Mapped[str]
    level: Mapped[str]                      # normal / urgent
    arrival_share: Mapped[float]
    mean_service_minutes: Mapped[float]


class ServiceWindow(Base):
    """窗口及其可办票种（allowed 存票种 code 列表）。"""
    __tablename__ = "service_windows"
    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("service_scenarios.id"))
    code: Mapped[str]
    name: Mapped[str]
    allowed: Mapped[list] = mapped_column(JSON)
