"""多票种抢占优先级仿真的独立重复驱动（纯标准库）。

与旧 FCFS 路径相同的试验护栏：500–10000 张/重复、warmup 至少保留100、5–40 重复、
总量 ≤250000；每重复从空系统开始，使用根种子派生的独立随机流（random.Random +
"spawn" 派生键），冻结快照与种子即可逐位复算。
"""
from __future__ import annotations

import math
import random

from .priority_algorithm import schedule_priority


def _child_rng(root_seed, replication, stream):
    """派生可复现子流：根种子 + 重复号 + 流号(0=到达,1=服务)。

    用独立 hash 域避免流间相关；旧 NumPy 路径记录 spawn_key，这里记录同样可读的派生键。
    """
    digest = f"queue-lab:priority:v1:{int(root_seed)}:{int(replication)}:{int(stream)}"
    seed = 0
    for ch in digest.encode("utf-8"):
        seed = (seed * 131 + ch) & 0xFFFFFFFFFFFFFFFF
    return random.Random(seed), [int(root_seed), int(replication), int(stream)]


def mean_t_interval(values, confidence=0.95):
    """Student-t 重复均值区间；无 SciPy 依赖时用正则化不完全 beta 函数反解 t 分位数。"""
    if len(values) < 2 or not all(math.isfinite(v) for v in values):
        raise ValueError("t区间至少需要2个有限重复均值")
    if not isinstance(confidence, (int, float)) or not 0.8 <= confidence <= 0.99:
        raise ValueError("置信水平须在[.8,.99]")
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    sd = math.sqrt(var)
    se = sd / math.sqrt(n)
    dof = n - 1
    critical = _t_ppf((1 + confidence) / 2, dof)
    return {"mean": mean, "lower": mean - critical * se, "upper": mean + critical * se,
            "standard_error": se, "degrees_of_freedom": dof, "critical_t": critical,
            "degenerate": sd == 0, "confidence": confidence}


def _beta_cf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def _betai(a, b, x):
    """正则化不完全 beta 函数 I_x(a,b)（Numerical Recipes 连分式）。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_cf(a, b, x) / a
    # 对称关系 I_x(a,b) = 1 - I_{1-x}(b,a)
    return 1.0 - math.exp(lbeta + b * math.log1p(-x) + a * math.log(x)) * _beta_cf(b, a, 1.0 - x) / b


def _t_sf(t_value, dof):
    x = dof / (dof + t_value * t_value)
    return 0.5 * _betai(dof / 2.0, 0.5, x)


def _t_ppf(p, dof):
    """对 Student-t 生存函数 1-p 做二分求分位数。"""
    target = 1.0 - p
    lo, hi = 0.0, 1.0
    while _t_sf(hi, dof) > target:
        hi *= 2.0
        if hi > 1e6:
            break
    for _ in range(100):
        mid = (lo + hi) / 2
        if _t_sf(mid, dof) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def simulate_priority_replicates(classes, windows, total_arrival_rate,
                                 customers=3000, warmup=500, replications=20,
                                 seed=2026, confidence=0.95):
    """按票种占比混合的 Poisson 到达、逐票种指数服务，执行抢占优先级独立重复。"""
    if not isinstance(customers, int) or not 500 <= customers <= 10000:
        raise ValueError("顾客500–10000")
    if not isinstance(warmup, int) or not 0 <= warmup <= 5000 or customers - warmup < 100:
        raise ValueError("warmup最多5000且至少保留100个顾客")
    if not isinstance(replications, int) or not 5 <= replications <= 40:
        raise ValueError("重复5–40次")
    if customers * replications > 250000:
        raise ValueError("单任务总顾客上限250000")
    if not isinstance(seed, int) or not 0 <= seed <= 2147483647:
        raise ValueError("随机种子须为0到2147483647整数")
    if not isinstance(total_arrival_rate, (int, float)) or not 1e-6 <= total_arrival_rate <= 1000:
        raise ValueError("总到达率须为[1e-6,1000]请求/分钟")

    shares = [float(c["arrival_share"]) for c in classes]
    boundaries = []
    acc = 0.0
    for s in shares:
        acc += s
        boundaries.append(acc)
    boundaries[-1] = 1.0  # 消除浮点尾差
    code_at = lambda u: next(classes[i]["code"] for i, b in enumerate(boundaries) if u <= b)

    results = []
    sample = []
    for r in range(replications):
        arrival_rng, arrival_key = _child_rng(seed, r, 0)
        service_rng, service_key = _child_rng(seed, r, 1)
        arrivals = {c["code"]: [] for c in classes}
        services = {c["code"]: [] for c in classes}
        clock = 0.0
        for _ in range(customers):
            clock += arrival_rng.expovariate(total_arrival_rate)
            code = code_at(arrival_rng.random())
            mean = float(next(c["mean_service_minutes"] for c in classes if c["code"] == code))
            arrivals[code].append(clock)
            services[code].append(service_rng.expovariate(1.0 / mean))
        sim = schedule_priority(classes, windows, arrivals, services, warmup)
        records = sim.pop("records")
        results.append({
            "replication": r + 1,
            "arrival_spawn_key": arrival_key,
            "service_spawn_key": service_key,
            **sim,
        })
        if r == 0:
            step = max(1, len(records) // 100)
            sample = records[::step]
            if sample[-1]["seq"] != records[-1]["seq"]:
                sample.append(records[-1])

    wait_values = [x["overall"]["mean_wait_minutes"] for x in results]
    system_values = [x["overall"]["mean_system_minutes"] for x in results]
    interval = mean_t_interval(wait_values, confidence)
    system_interval = mean_t_interval(system_values, confidence)

    # 跨重复汇总票种统计（均值类取重复均值；累计类取重复求和后再均值，便于页面展示）。
    per_ticket_summary = []
    for c in classes:
        t = c["code"]
        rows = [next(p for p in rep["per_ticket"] if p["ticket"] == t) for rep in results]
        per_ticket_summary.append({
            "ticket": t,
            "level": c["level"],
            "arrival_share": float(c["arrival_share"]),
            "mean_service_minutes": float(c["mean_service_minutes"]),
            "mean_arrivals": sum(x["arrivals"] for x in rows) / len(rows),
            "mean_retained": sum(x["retained"] for x in rows) / len(rows),
            "mean_completed": sum(x["completed"] for x in rows) / len(rows),
            "cumulative_wait_minutes": sum(x["cumulative_wait_minutes"] for x in rows) / len(rows),
            "total_cumulative_wait_minutes": sum(x["cumulative_wait_minutes"] for x in rows),
            "mean_wait_minutes": sum(x["mean_wait_minutes"] for x in rows) / len(rows),
            "mean_system_minutes": sum(x["mean_system_minutes"] for x in rows) / len(rows),
            "wait_probability": sum(x["wait_probability"] for x in rows) / len(rows),
            "max_wait_minutes": max(x["max_wait_minutes"] for x in rows),
            "preemptions": sum(x["preemptions"] for x in rows),
            "mean_preemptions": sum(x["preemptions"] for x in rows) / len(rows),
            "preempted_jobs": sum(x["preempted_jobs"] for x in rows),
            "mean_service_demand_minutes": sum(x["total_service_demand_minutes"] for x in rows) / len(rows),
            "mean_served_minutes": sum(x["served_minutes"] for x in rows) / len(rows),
        })

    # 跨重复守恒核对：每重复都必须平衡，再汇总平均服务量。
    conservation_all = [rep["conservation"] for rep in results]
    conservation = {
        "all_replications_balanced": all(x["balanced"] for x in conservation_all),
        "mean_total_service_demand_minutes": sum(x["total_service_demand_minutes"] for x in conservation_all) / len(results),
        "mean_served_minutes": sum(x["served_minutes"] for x in conservation_all) / len(results),
        "mean_remaining_minutes": sum(x["remaining_minutes"] for x in conservation_all) / len(results),
        "mean_window_busy_minutes_full_horizon": sum(x["window_busy_minutes_full_horizon"] for x in conservation_all) / len(results),
        "max_abs_demand_gap": max(abs(x["demand_minus_served_minus_remaining"]) for x in conservation_all),
        "max_abs_busy_gap": max(abs(x["served_minus_window_busy"]) for x in conservation_all),
    }

    return {
        "mode": "multi_class_preemptive_priority",
        "ticket_classes": classes,
        "windows": windows,
        "total_arrival_rate": total_arrival_rate,
        "replications": results,
        "per_ticket_summary": per_ticket_summary,
        "wait_interval": interval,
        "system_interval": system_interval,
        "mean_wait_probability": sum(x["overall"]["wait_probability"] for x in results) / len(results),
        "mean_busy_fraction_window": sum(x["overall"]["busy_fraction_window"] for x in results) / len(results),
        "total_preemptions": sum(x["overall"]["preemptions"] for x in results),
        "conservation": conservation,
        "sample_customers": sample,
        "customers": customers,
        "warmup": warmup,
        "retained_per_replication": customers - warmup,
        "replication_count": replications,
        "seed": seed,
        "analytical": None,  # 多票种抢占+异构窗口无适用单一解析值，由上层显式说明
        "assumptions": ("按票种占比混合的Poisson到达、逐票种独立指数服务；急件可抢占普通票，"
                        "被中断票保留剩余服务量并可换兼容窗口续办；同刻完成先于到达，同级先到先办；"
                        "每重复从空系统开始，暖机按全局到达顺序剔除前warmup张票。"),
        "analytical_note": ("本情景为多票种、异速服务、窗口可办票种受限且含抢占续办，"
                            "不存在可直接套用的单一M/M/c Erlang-C解析值；仅提供有限顾客仿真结果与重复均值t区间。"),
        "ci_note": ("区间是独立重复的平均等待均值t区间，不是顾客独立样本区间；不含模型或暖机偏差，未经非负截断。"),
        "finite_window_note": ("仿真生成固定票数并服务至全部完成；忙碌率窗口从首个保留票到达到全部票完成，"
                               "含排空效应，不等于任何稳态解析值。"),
        "rng_note": "随机流由根种子按(重复号,流号)派生，冻结快照与种子可复算；到达流0、服务流1。",
    }
