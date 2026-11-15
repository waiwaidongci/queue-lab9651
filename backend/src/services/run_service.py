from fastapi import HTTPException
from redis import Redis
from ..config.settings import REDIS_URL
from ..models import SimulationRun, ServiceScenario, ArrivalProfile, QueueStudy, CapacityNote
from ..models import TicketClassConfig, ServiceWindow
from ..utils.serialize import record
from .erlang_algorithm import erlang_c
from .export_builder import export_fcfs, export_priority
from .audit_service import log

queue = Redis.from_url(REDIS_URL, decode_responses=True)


def list_runs(db):
    return [record(r) for r in db.query(SimulationRun).order_by(SimulationRun.id.desc())]


def get_run(db, rid):
    row = db.get(SimulationRun, rid)
    if not row:
        raise HTTPException(404, "运行不存在")
    return row


def create_snapshot(db, scenario):
    profile = db.get(ArrivalProfile, scenario.profile_id)
    study = db.get(QueueStudy, profile.study_id)
    snapshot = {"study": record(study), "profile": record(profile),
                "scenario": record(scenario), "time_unit": "minutes",
                "rate_unit": "requests/minute"}
    if scenario.mode == "priority":
        snapshot["ticket_classes"] = [
            record(c) for c in db.query(TicketClassConfig)
            .filter_by(scenario_id=scenario.id).order_by(TicketClassConfig.id)]
        snapshot["windows"] = [
            record(w) for w in db.query(ServiceWindow)
            .filter_by(scenario_id=scenario.id).order_by(ServiceWindow.id)]
    return snapshot


def create_run(db, data, user):
    scenario = db.get(ServiceScenario, data.scenario_id)
    if not scenario:
        raise HTTPException(404, "服务情景不存在")
    snapshot = create_snapshot(db, scenario)
    if scenario.mode != "priority":
        # 旧单队列路径保留 Erlang-C 稳态护栏。
        try:
            erlang_c(snapshot["profile"]["arrival_rate"],
                     1 / scenario.mean_service_minutes, scenario.servers)
        except ValueError as e:
            raise HTTPException(422, str(e))
    else:
        # 多票种路径的粗负荷护栏（与 comparison_service 内的计算一致，提前在入队前拒绝）。
        total_rate = scenario.total_arrival_rate or snapshot["profile"]["arrival_rate"]
        weighted = sum(c["arrival_share"] * c["mean_service_minutes"]
                       for c in snapshot["ticket_classes"])
        if total_rate * weighted >= scenario.servers:
            raise HTTPException(
                422, "总负荷达到或超过窗口总能力，队列无稳态，拒绝运行；请降低到达率或增加窗口")
    if data.customers - data.warmup < 100 or data.customers * data.replications > 250000:
        raise HTTPException(422, "至少保留100顾客，且单任务总顾客不超过250000")
    row = SimulationRun(**data.model_dump(), input_snapshot=snapshot, owner=user.name)
    db.add(row)
    db.flush()
    log(db, user.email, "simulation.enqueue", row.id)
    db.commit()
    try:
        queue.rpush("queue:jobs", row.id)
    except Exception:
        row.status = "failed"
        row.error = "队列不可用，请重新提交"
        db.commit()
        raise HTTPException(503, row.error)
    return record(row)


def export_run(db, rid):
    row = get_run(db, rid)
    if row.status != "completed" or not db.query(CapacityNote).filter_by(
            run_id=rid, status="approved").first():
        raise HTTPException(403, "仅获批的完成运行可导出")
    result = row.result
    if result.get("mode") == "multi_class_preemptive_priority":
        return export_priority(row.id, result)
    return export_fcfs(result)
