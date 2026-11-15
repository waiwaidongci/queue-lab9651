import uuid
from fastapi import HTTPException
from ..models import ServiceScenario, ArrivalProfile, TicketClassConfig, ServiceWindow
from ..utils.serialize import record
from .audit_service import log
from .priority_algorithm import _validate_spec


def _priority_payload(db, s):
    classes = [{"code": c.code, "name": c.name, "level": c.level,
                "arrival_share": c.arrival_share, "mean_service_minutes": c.mean_service_minutes}
               for c in db.query(TicketClassConfig).filter_by(scenario_id=s.id).order_by(TicketClassConfig.id)]
    windows = [{"code": w.code, "name": w.name, "allowed": w.allowed}
               for w in db.query(ServiceWindow).filter_by(scenario_id=s.id).order_by(ServiceWindow.id)]
    return classes, windows


def serialize_scenario(db, s):
    p = db.get(ArrivalProfile, s.profile_id)
    mu = 1 / s.mean_service_minutes
    rho = p.arrival_rate / (s.servers * mu)
    data = dict(record(s), arrival_rate=p.arrival_rate, service_rate=mu,
                utilization=rho, stable=rho < 1, profile_name=p.name)
    if s.mode == "priority":
        classes, windows = _priority_payload(db, s)
        data["ticket_classes"] = classes
        data["window_configs"] = windows
        data["effective_arrival_rate"] = s.total_arrival_rate or p.arrival_rate
        # 多票种、受限可办窗口且含抢占续办，无单一 M/M/c 稳态解析值。
        data["stable"] = True  # 稳定性在运行护栏中按总负荷粗校验，页面不展示 Erlang 拒绝逻辑
        data["analytical_available"] = False
    else:
        data["ticket_classes"] = []
        data["window_configs"] = []
        data["effective_arrival_rate"] = p.arrival_rate
        data["analytical_available"] = True
    return data


def list_scenarios(db):
    return [serialize_scenario(db, s) for s in db.query(ServiceScenario).order_by(ServiceScenario.id.desc())]


def _validate_priority_input(data):
    if len(data.ticket_classes) < 2:
        raise HTTPException(422, "多票种情景至少配置两个票种")
    codes = [c.code for c in data.ticket_classes]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, "票种 code 不可重复")
    share_sum = sum(c.arrival_share for c in data.ticket_classes)
    if abs(share_sum - 1.0) > 1e-6:
        raise HTTPException(422, f"各票种到达占比之和必须等于1，当前为{share_sum:.4f}")
    if len(data.windows) != data.servers:
        raise HTTPException(422, "窗口配置数量必须等于服务台数量 servers")
    w_codes = [w.code for w in data.windows]
    if len(set(w_codes)) != len(w_codes):
        raise HTTPException(422, "窗口 code 不可重复")
    classes = [c.model_dump() for c in data.ticket_classes]
    windows = [w.model_dump() for w in data.windows]
    try:
        _validate_spec(classes, windows)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return classes, windows


def create_scenario(db, data, user):
    if not db.get(ArrivalProfile, data.profile_id):
        raise HTTPException(404, "到达配置不存在")
    if db.query(ServiceScenario).filter_by(name=data.name).first():
        raise HTTPException(409, "情景名称已存在")
    mode = data.mode
    classes = windows = None
    if mode == "priority":
        classes, windows = _validate_priority_input(data)
    row = ServiceScenario(
        code="SC-" + uuid.uuid4().hex[:10], name=data.name, profile_id=data.profile_id,
        servers=data.servers, mean_service_minutes=data.mean_service_minutes,
        owner=user.name, mode=mode,
        total_arrival_rate=data.total_arrival_rate if mode == "priority" else None,
    )
    db.add(row)
    db.flush()
    if mode == "priority":
        for c in data.ticket_classes:
            db.add(TicketClassConfig(scenario_id=row.id, code=c.code, name=c.name, level=c.level,
                                     arrival_share=c.arrival_share,
                                     mean_service_minutes=c.mean_service_minutes))
        for w in data.windows:
            db.add(ServiceWindow(scenario_id=row.id, code=w.code, name=w.name or w.code, allowed=w.allowed))
    log(db, user.email, "scenario.create", row.code)
    db.commit()
    return serialize_scenario(db, row)
