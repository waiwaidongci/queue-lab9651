"""多票种抢占式优先级窗口调度（纯标准库，无新依赖）。

业务规则
--------
* 票种 (ticket class)：到达占比 share、平均服务时长 mean_service_minutes、等级 normal/urgent。
* 窗口 (window)：只可处理兼容票种（allowed 列表）。
* 空窗分配：先使急件(urgent)开工数最多，再使总开工数最多；同级按到达先后（同刻按票种/票序号）。
* 急件到达时若无可用兼容窗口，可抢占正在服务普通票的兼容窗口；被中断票保留剩余服务量并可换到
  任意兼容窗口续办；每张票每次被抢占计一次抢占。
* 同一时刻：服务完成事件先于到达事件处理（同刻完成先于到达）。
* 等待 = 开工前所有未在窗口内接受服务的累计时间（含被抢占后的再等待）。

实现用逐票种的堆等待队列，事件与分配均为对数/小常数复杂度；随机数生成由调用方注入以保证复算。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

NORMAL = "normal"
URGENT = "urgent"
LEVELS = (NORMAL, URGENT)
LEVEL_RANK = {URGENT: 0, NORMAL: 1}  # 数值越小优先级越高


@dataclass
class Job:
    seq: int                 # 全局到达顺序（同刻按票种等级、票种 code、票序号确定）
    ticket: str              # 票种 code
    level: str               # normal / urgent
    arrival: float           # 到达时刻
    service: float           # 初始服务需求量（分钟）
    remaining: float         # 剩余服务量（被抢占后保留）
    waits: list = field(default_factory=list)  # 各段等待区间 (from,to)
    preemptions: int = 0
    start: float | None = None
    completion: float | None = None
    window: int | None = None
    served_segments: list = field(default_factory=list)  # (window,start,finish)
    waiting_since: float | None = None

    @property
    def total_wait(self) -> float:
        return sum(b - a for a, b in self.waits)


@dataclass
class _Occupancy:
    job_seq: int
    started: float           # 当前服务段开始时刻
    finish: float            # 当前段预计完成时刻
    initial_demand: float    # 该票进入本段时的剩余量
    seg_id: int              # 服务段令牌：被抢占后旧完成事件凭此判为陈旧事件


def _validate_spec(classes, windows):
    if not isinstance(classes, list) or not classes:
        raise ValueError("至少配置一个票种")
    if not isinstance(windows, list) or not windows:
        raise ValueError("至少配置一个窗口")
    codes = [c["code"] for c in classes]
    if len(set(codes)) != len(codes):
        raise ValueError("票种 code 不可重复")
    share_sum = 0.0
    for c in classes:
        if c.get("level") not in LEVELS:
            raise ValueError("票种等级必须是 normal 或 urgent")
        share = c.get("arrival_share")
        mean = c.get("mean_service_minutes")
        if not isinstance(share, (int, float)) or not math.isfinite(share) or share <= 0:
            raise ValueError("票种到达占比须为正数")
        if not isinstance(mean, (int, float)) or not math.isfinite(mean) or not 0.001 <= mean <= 120:
            raise ValueError("票种平均服务时长须在[0.001,120]分钟")
        share_sum += float(share)
    if abs(share_sum - 1.0) > 1e-9:
        raise ValueError("各票种到达占比之和必须等于1")
    if len(windows) > 20:
        raise ValueError("窗口数量最多20个")
    allowed_map = {}
    for i, w in enumerate(windows):
        allowed = w.get("allowed", [])
        if not isinstance(allowed, list) or not allowed:
            raise ValueError("每个窗口至少配置一个可办票种")
        unknown = [t for t in allowed if t not in codes]
        if unknown:
            raise ValueError(f"窗口{i + 1}配置了不存在的票种: {unknown}")
        allowed_map[i] = list(allowed)
    for code in codes:
        if not any(code in allowed_map[i] for i in allowed_map):
            raise ValueError(f"票种 {code} 没有任何可办窗口，无法被服务")
    return allowed_map


def schedule_priority(classes, windows, arrivals_by_class, services_by_class, warmup=0):
    """执行一次多票种抢占式优先级仿真。

    arrivals_by_class[ticket]：该票种每个票的到达时刻（升序、非负）。
    services_by_class[ticket]：与到达等长的初始服务需求量（正数）。
    warmup：按全局到达顺序剔除前 warmup 张票（仅统计剔除，不重置系统）。
    返回每票种统计、总体统计、逐票事件与服务量守恒核对。
    """
    allowed_map = _validate_spec(classes, windows)
    spec = {c["code"]: c for c in classes}
    n_windows = len(windows)
    codes = [c["code"] for c in classes]

    # 合并各票种到达流：同刻先急后普通，再按票种 code、票内序号，保证确定且可复算。
    merged = []
    for c in classes:
        t = c["code"]
        aa = arrivals_by_class[t]
        ss = services_by_class[t]
        if len(aa) != len(ss) or not aa:
            raise ValueError(f"票种 {t} 的到达/服务数组须等长且非空")
        if any(b < a for a, b in zip(aa, aa[1:])):
            raise ValueError(f"票种 {t} 到达时刻必须升序")
        for k, (a, s) in enumerate(zip(aa, ss)):
            if not (math.isfinite(a) and a >= 0 and math.isfinite(s) and s > 0):
                raise ValueError("到达时刻须非负有限、服务量须正有限")
            merged.append((float(a), LEVEL_RANK[c["level"]], t, k))
    merged.sort()
    total_jobs = len(merged)
    if not isinstance(warmup, int) or not 0 <= warmup < total_jobs:
        raise ValueError("warmup 必须是非负整数且小于总票数")

    jobs: list[Job] = []
    for seq, (arrival, _rank, ticket, k) in enumerate(merged):
        service = float(services_by_class[ticket][k])
        jobs.append(Job(seq=seq, ticket=ticket, level=spec[ticket]["level"],
                        arrival=arrival, service=service, remaining=service))

    # 逐票种等待堆：元素 (arrival, seq)；arrival 同级 FCFS，seq 为同刻稳定决胜。
    waiting_heaps = {t: [] for t in codes}
    # 事件堆：(time, kind, seq, seg_id)。kind 0=完成（先），1=到达（后），同刻完成先于到达。
    events = [(j.arrival, 1, j.seq, -1) for j in jobs]
    heapq.heapify(events)
    occupancy: dict[int, _Occupancy] = {}
    free_windows: set[int] = set(range(n_windows))
    next_seg_id = 0
    # 窗口灵活度：兼容票种数；分配时优先最不灵活窗口，为急件保留通办窗口。
    flexibility = [len(allowed_map[w]) for w in range(n_windows)]

    def start_job(seq, window, now):
        nonlocal next_seg_id
        job = jobs[seq]
        if job.waiting_since is not None:
            job.waits.append((job.waiting_since, now))
            job.waiting_since = None
        if job.start is None:
            job.start = now
        job.window = window
        free_windows.discard(window)
        demand = job.remaining
        seg_id = next_seg_id
        next_seg_id += 1
        occupancy[window] = _Occupancy(job_seq=seq, started=now, finish=now + demand,
                                       initial_demand=demand, seg_id=seg_id)
        heapq.heappush(events, (now + demand, 0, seq, seg_id))

    def enqueue_wait(seq, now):
        job = jobs[seq]
        if job.waiting_since is None:
            job.waiting_since = now
            heapq.heappush(waiting_heaps[job.ticket], (job.arrival, seq))
        # waiting_since 非空表示已在等待堆中，不重复入堆（陈旧条目由 _valid_head 过滤）。

    def _valid_head(t):
        """返回票种 t 等待堆的有效堆顶 (arrival, seq)，顺带清理陈旧条目。"""
        h = waiting_heaps[t]
        while h:
            arrival, seq = h[0]
            if jobs[seq].window is None and jobs[seq].remaining > 1e-12:
                return arrival, seq
            heapq.heappop(h)
        return None

    def pop_candidates(level, limit):
        """取该等级 FCFS 最早的至多 limit 张等待票（跨票种堆顶 k 路归并）。

        匹配基数不超过空窗数，故只需 limit 张，避免深队列下每次事件排空整个等待堆。
        未匹配者由调用方按 (arrival, seq) 放回，堆性质不变。
        """
        picked = []
        for _ in range(limit):
            best = None
            for t in codes:
                if spec[t]["level"] != level:
                    continue
                head = _valid_head(t)
                if head is not None and (best is None or head < best):
                    best = (*head, t)
            if best is None:
                break
            arrival, seq, t = best
            heapq.heappop(waiting_heaps[t])
            picked.append(seq)
        return picked

    def max_matching(candidate_seqs, free_list):
        """候选票与空窗的最大基数二分匹配（Kuhn 增广路）。

        候选按 FCFS 顺序处理、邻接窗按（灵活度、编号）排序，因此在所有最大基数匹配中
        倾向让到达更早的票先获配，满足“先最大化开工数、同级再先到先办”的层级目标。
        返回 [(seq, window), ...]。
        """
        adjacency = []
        for seq in candidate_seqs:
            ticket = jobs[seq].ticket
            adjacency.append([w for w in free_list if ticket in allowed_map[w]])
        match_window = {}  # window -> candidate index

        def augment(i, seen):
            for w in adjacency[i]:
                if w in seen:
                    continue
                seen.add(w)
                if w not in match_window or augment(match_window[w], seen):
                    match_window[w] = i
                    return True
            return False

        for i in range(len(candidate_seqs)):
            augment(i, set())
        return [(candidate_seqs[i], w) for w, i in match_window.items()]

    def allocate(now):
        """空窗分配：先用最大匹配使急件开工数最多，再对剩余空窗匹配普通票使总开工数最多；
        同级在最大基数前提下按到达先后（FCFS）优先。"""
        if not free_windows:
            return
        free_list = sorted(free_windows, key=lambda x: (flexibility[x], x))
        # 1) 急件优先匹配（候选数不超过空窗数）。
        urgent_seqs = pop_candidates(URGENT, len(free_list))
        urgent_matches = max_matching(urgent_seqs, free_list)
        matched_seqs = {s for s, _ in urgent_matches}
        for s in urgent_seqs:  # 未匹配急件放回等待堆
            if s not in matched_seqs:
                heapq.heappush(waiting_heaps[jobs[s].ticket], (jobs[s].arrival, s))
        for s, w in urgent_matches:
            start_job(s, w, now)
        # 2) 剩余空窗再匹配普通票，使总开工数最大。
        remaining_free = sorted(free_windows, key=lambda x: (flexibility[x], x))
        if remaining_free:
            normal_seqs = pop_candidates(NORMAL, len(remaining_free))
            normal_matches = max_matching(normal_seqs, remaining_free)
            matched_n = {s for s, _ in normal_matches}
            for s in normal_seqs:
                if s not in matched_n:
                    heapq.heappush(waiting_heaps[jobs[s].ticket], (jobs[s].arrival, s))
            for s, w in normal_matches:
                start_job(s, w, now)

    def reassign_with_preemption(now):
        """急件到达后若无兼容空窗：在“可抢占窗口（兼容且其上为普通票）”上对等待急件做最大匹配，
        使急件开工数达到最大；急件不抢占急件。被抢普通票保留剩余量并入等待，最后补常规空窗分配。"""
        # 可抢占窗口集合：已占用、当前是普通票。
        preemptible = [w for w in range(n_windows)
                       if (occ := occupancy.get(w)) is not None
                       and jobs[occ.job_seq].level == NORMAL]
        if not preemptible:
            return
        urgent_seqs = pop_candidates(URGENT, len(preemptible))
        if not urgent_seqs:
            return
        # 只在与该急件票种兼容的可抢占窗上匹配。
        matches = max_matching(urgent_seqs, preemptible)
        matched = {s for s, _ in matches}
        for s in urgent_seqs:  # 未获配急件放回等待
            if s not in matched:
                heapq.heappush(waiting_heaps[jobs[s].ticket], (jobs[s].arrival, s))
        for s, w in matches:
            occ = occupancy[w]
            victim = jobs[occ.job_seq]
            served = now - occ.started
            victim.remaining = max(0.0, occ.initial_demand - served)
            victim.served_segments.append((w + 1, occ.started, now))
            victim.preemptions += 1
            victim.window = None
            victim.waiting_since = now  # 即刻重新累计等待，可换兼容窗口续办
            heapq.heappush(waiting_heaps[victim.ticket], (victim.arrival, victim.seq))
            del occupancy[w]
            free_windows.add(w)
            start_job(s, w, now)
        allocate(now)

    while events:
        now, kind, seq, seg_id = heapq.heappop(events)
        job = jobs[seq]
        if kind == 0:
            window = job.window
            occ = occupancy.get(window)
            # 段令牌不匹配即被抢占后的陈旧完成事件，直接丢弃。
            if occ is None or occ.job_seq != seq or occ.seg_id != seg_id:
                continue
            # 真正完成：同刻完成先于到达，在任何同刻到达之前落账。
            job.remaining = 0.0
            job.completion = now
            job.served_segments.append((window + 1, occ.started, now))
            job.window = None
            del occupancy[window]
            free_windows.add(window)
            allocate(now)
        else:
            # 先常规空窗分配（急件优先于同刻/既有普通等待票）。
            enqueue_wait(seq, now)
            allocate(now)
            if job.remaining > 0 and job.window is None and job.level == URGENT:
                # 急件仍在等待：级联抢占重排。
                reassign_with_preemption(now)

    if any(j.completion is None for j in jobs):
        raise RuntimeError("存在未完成票，调度异常")

    return _summarize(jobs, classes, windows, warmup)


def _summarize(jobs, classes, windows, warmup):
    n_windows = len(windows)
    retained = jobs[warmup:]
    begin = retained[0].arrival
    end = max(j.completion for j in jobs)
    duration = max(end - begin, 1e-12)

    # 窗口忙碌：clip 口径用于观察窗口忙碌率；full 口径覆盖全时域，用于服务量守恒核对。
    busy_by_window = [0.0] * n_windows
    busy_full_by_window = [0.0] * n_windows
    for j in jobs:
        for win_no, s, f in j.served_segments:
            busy_by_window[win_no - 1] += max(0.0, min(f, end) - max(s, begin))
            busy_full_by_window[win_no - 1] += f - s

    per_class = []
    for c in classes:
        t = c["code"]
        members = [j for j in jobs if j.ticket == t]
        kept = [j for j in retained if j.ticket == t]
        waits = [j.total_wait for j in kept]
        systems = [j.completion - j.arrival for j in kept]
        served = sum(j.service - j.remaining for j in members)
        per_class.append({
            "ticket": t,
            "level": c["level"],
            "arrival_share": float(c["arrival_share"]),
            "mean_service_minutes": float(c["mean_service_minutes"]),
            "arrivals": len(members),
            "retained": len(kept),
            "completed": len(kept),
            "cumulative_wait_minutes": float(sum(waits)),
            "mean_wait_minutes": float(sum(waits) / len(waits)) if waits else 0.0,
            "mean_system_minutes": float(sum(systems) / len(systems)) if systems else 0.0,
            "wait_probability": (sum(1 for w in waits if w > 1e-12) / len(waits)) if waits else 0.0,
            "max_wait_minutes": float(max(waits)) if waits else 0.0,
            "preemptions": sum(j.preemptions for j in kept),
            "preempted_jobs": sum(1 for j in kept if j.preemptions > 0),
            "total_service_demand_minutes": float(sum(j.service for j in members)),
            "served_minutes": float(served),
            "remaining_minutes": float(sum(j.remaining for j in members)),
        })

    all_waits = [j.total_wait for j in retained]
    total_demand = sum(j.service for j in jobs)
    total_served = sum(j.service - j.remaining for j in jobs)
    total_remaining = sum(j.remaining for j in jobs)
    busy_total = sum(busy_by_window)
    busy_full_total = sum(busy_full_by_window)

    # 服务量守恒：初始需求 == 已服务 + 剩余（全部完成后剩余应为0）；
    # 全时域窗口忙碌必须与已服务量逐分钟相等（被抢占票可换窗续办，服务量不丢失）。
    conservation = {
        "scope": "all_jobs_full_horizon",
        "total_service_demand_minutes": float(total_demand),
        "served_minutes": float(total_served),
        "remaining_minutes": float(total_remaining),
        "window_busy_minutes_full_horizon": float(busy_full_total),
        "demand_minus_served_minus_remaining": float(total_demand - total_served - total_remaining),
        "served_minus_window_busy": float(total_served - busy_full_total),
        "balanced": abs(total_demand - total_served - total_remaining) <= 1e-9
                    and abs(total_served - busy_full_total) <= 1e-9
                    and total_remaining <= 1e-9,
    }
    retained_conservation = {
        "scope": "retained_jobs",
        "total_service_demand_minutes": float(sum(j.service for j in retained)),
        "served_minutes": float(sum(j.service - j.remaining for j in retained)),
        "note": "保留票若在观察窗口前已被部分服务，窗口忙碌口径含跨边界区间，差异属暖机/尾部边界而非丢失。",
    }

    records = [{
        "seq": j.seq + 1, "ticket": j.ticket, "level": j.level,
        "arrival": j.arrival, "first_start": j.start, "completion": j.completion,
        "window": (j.served_segments[0][0] if j.served_segments else None),
        "windows_used": [w for w, _s, _f in j.served_segments],
        "wait": j.total_wait, "system": j.completion - j.arrival,
        "service_demand": j.service, "preemptions": j.preemptions,
        "retained": j.seq >= warmup,
    } for j in jobs]

    return {
        "per_ticket": per_class,
        "overall": {
            "arrivals": len(jobs),
            "retained": len(retained),
            "completed": len(retained),
            "windows": n_windows,
            "cumulative_wait_minutes": float(sum(all_waits)),
            "mean_wait_minutes": float(sum(all_waits) / len(all_waits)) if all_waits else 0.0,
            "mean_system_minutes": float(sum(j.completion - j.arrival for j in retained) / len(retained)),
            "wait_probability": (sum(1 for w in all_waits if w > 1e-12) / len(all_waits)) if all_waits else 0.0,
            "max_wait_minutes": float(max(all_waits)) if all_waits else 0.0,
            "preemptions": sum(j.preemptions for j in retained),
            "preempted_jobs": sum(1 for j in retained if j.preemptions > 0),
            "window_busy_minutes": float(busy_total),
            "window_busy_minutes_full_horizon": float(busy_full_total),
            "window_capacity_minutes": float(n_windows * duration),
            "busy_fraction_window": float(busy_total / (n_windows * duration)),
            "window_minutes": float(duration),
        },
        "conservation": conservation,
        "retained_conservation": retained_conservation,
        "window_busy_minutes": busy_by_window,
        "window_busy_minutes_full_horizon": busy_full_by_window,
        "records": records,
    }
