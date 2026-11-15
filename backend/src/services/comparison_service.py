from .simulation_algorithm import simulate_replicates
from .priority_simulation import simulate_priority_replicates
from ..utils.fingerprint import fingerprint


def calculate_run(db, snapshot, customers, warmup, replications, seed, confidence):
    """根据快照模式分派：旧 FCFS/Erlang-C 路径或新多票种抢占优先级路径。"""
    s = snapshot["scenario"]
    p = snapshot["profile"]
    if s.get("mode") == "priority":
        classes = snapshot["ticket_classes"]
        windows = snapshot["windows"]
        total_rate = s.get("total_arrival_rate") or p["arrival_rate"]
        # 粗负荷护栏：加权平均服务需求 × 总到达率 不得超过窗口总服务能力。
        weighted_mean_service = sum(c["arrival_share"] * c["mean_service_minutes"] for c in classes)
        offered_load = total_rate * weighted_mean_service
        capacity = len(windows)
        if offered_load >= capacity:
            raise ValueError(
                f"总负荷 {offered_load:.3f} 分钟/分钟 ≥ 窗口总能力 {capacity}，系统无稳态且队列会无限增长，拒绝运行")
        result = simulate_priority_replicates(
            classes, windows, total_rate, customers, warmup, replications, seed, confidence)
        result["input_snapshot"] = snapshot
        result["input_hash"] = fingerprint({
            "method": "multiclass-preemptive-priority-v1", "snapshot": snapshot,
            "customers": customers, "warmup": warmup, "replications": replications,
            "seed": seed, "confidence": confidence})
        result["method_version"] = "multiclass-preemptive-priority-v1"
        return result

    result = simulate_replicates(
        p["arrival_rate"], 1 / s["mean_service_minutes"], s["servers"],
        customers, warmup, replications, seed, confidence)
    result["input_snapshot"] = snapshot
    result["input_hash"] = fingerprint({
        "method": "erlangc-fcfs-independent-t-v1", "snapshot": snapshot,
        "customers": customers, "warmup": warmup, "replications": replications,
        "seed": seed, "confidence": confidence})
    result["method_version"] = "erlangc-fcfs-independent-t-v1"
    return result
