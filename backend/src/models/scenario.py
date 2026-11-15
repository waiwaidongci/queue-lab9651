from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..config.database import Base


class ServiceScenario(Base):
    __tablename__ = "service_scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(unique=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("arrival_profiles.id"))
    servers: Mapped[int]
    mean_service_minutes: Mapped[float]
    owner: Mapped[str]
    # fcfs：旧单队列 M/M/c 路径（默认，旧数据可读）；
    # priority：多票种抢占优先级路径，票种与窗口配置存于关联表。
    mode: Mapped[str] = mapped_column(default="fcfs")
    # 多票种路径使用的总到达率（请求/分钟）；为空时回退到达配置的 arrival_rate。
    total_arrival_rate: Mapped[float | None] = mapped_column(nullable=True)
