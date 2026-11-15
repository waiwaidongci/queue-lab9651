"""获批运行 CSV 导出的纯函数构造器（不依赖数据库/框架，便于离线核对）。"""
import csv
import io


def export_fcfs(result):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["replication", "mean_wait_minutes", "mean_system_minutes", "wait_probability",
                "busy_fraction_window", "window_minutes", "retained_customers",
                "arrival_spawn_key", "service_spawn_key", "analytic_wait_minutes", "input_hash"])
    for x in result["replications"]:
        w.writerow([x[k] for k in ["replication", "mean_wait_minutes", "mean_system_minutes",
                                   "wait_probability", "busy_fraction_window", "window_minutes",
                                   "retained_customers", "arrival_spawn_key",
                                   "service_spawn_key"]]
                   + [result["analytical"]["mean_wait_minutes"], result["input_hash"]])
    return out.getvalue()


def export_priority(run_id, result):
    """多票种抢占路径：票种级累计等待、抢占、完成与服务量守恒，可逐行核对。"""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["# 多票种抢占优先级运行", f"run_id={run_id}", f"seed={result['seed']}",
                f"method={result['method_version']}", f"input_hash={result['input_hash']}"])
    w.writerow([])
    w.writerow(["ticket", "level", "arrival_share", "mean_service_minutes",
                "mean_arrivals", "mean_completed", "total_cumulative_wait_minutes",
                "mean_wait_minutes", "wait_probability", "total_preemptions",
                "preempted_jobs", "mean_service_demand_minutes", "mean_served_minutes"])
    for c in result["per_ticket_summary"]:
        w.writerow([c["ticket"], c["level"], c["arrival_share"], c["mean_service_minutes"],
                    c["mean_arrivals"], c["mean_completed"], c["total_cumulative_wait_minutes"],
                    c["mean_wait_minutes"], c["wait_probability"], c["preemptions"],
                    c["preempted_jobs"], c["mean_service_demand_minutes"], c["mean_served_minutes"]])
    cons = result["conservation"]
    w.writerow([])
    w.writerow(["conservation_check", "value"])
    for k, v in cons.items():
        w.writerow([k, v])
    w.writerow([])
    w.writerow(["replication", "mean_wait_minutes", "mean_system_minutes", "wait_probability",
                "preemptions", "busy_fraction_window", "window_minutes", "retained_customers",
                "served_minutes", "window_busy_minutes_full_horizon",
                "demand_minus_served_minus_remaining", "arrival_spawn_key", "service_spawn_key"])
    for x in result["replications"]:
        o = x["overall"]
        c = x["conservation"]
        w.writerow([x["replication"], o["mean_wait_minutes"], o["mean_system_minutes"],
                    o["wait_probability"], o["preemptions"], o["busy_fraction_window"],
                    o["window_minutes"], o["retained"], c["served_minutes"],
                    c["window_busy_minutes_full_horizon"],
                    c["demand_minus_served_minus_remaining"],
                    ".".join(map(str, x["arrival_spawn_key"])),
                    ".".join(map(str, x["service_spawn_key"]))])
    w.writerow([])
    w.writerow(["analytical_note", result["analytical_note"]])
    return out.getvalue()
