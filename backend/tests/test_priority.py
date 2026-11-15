"""多票种抢占调度的纯标准库离线核对（无需 numpy/数据库）。

运行：cd backend && python -m tests.test_priority
"""
import math
import random
import unittest

from src.services.priority_algorithm import (
    URGENT, NORMAL, schedule_priority,
)


def expo(rng, rate):
    return rng.expovariate(rate)


class PrioritySchedulerTests(unittest.TestCase):
    def _basic_spec(self):
        classes = [
            {"code": "URG", "level": URGENT, "arrival_share": 0.3, "mean_service_minutes": 4.0},
            {"code": "NRM", "level": NORMAL, "arrival_share": 0.7, "mean_service_minutes": 6.0},
        ]
        windows = [
            {"code": "W1", "allowed": ["URG", "NRM"]},
            {"code": "W2", "allowed": ["NRM"]},
        ]
        return classes, windows

    def test_urgent_preempts_normal_and_preserves_remaining(self):
        # 两张普通票占满两窗，急件到达抢占 W1（唯一兼容急件的窗口）。
        classes, windows = self._basic_spec()
        arrivals = {"NRM": [0.0, 0.0], "URG": [1.0]}
        # NRM 服务量 10：到 t=1 被抢占时已服务1，剩余9；窗口 W2 只办普通票。
        services = {"NRM": [10.0, 10.0], "URG": [4.0]}
        out = schedule_priority(classes, windows, arrivals, services, warmup=0)
        by_ticket = {}
        for r in out["records"]:
            by_ticket.setdefault(r["ticket"], []).append(r)
        urgent = by_ticket["URG"][0]
        # 急件 t=1 立即开工（抢占），t=5 完成，无等待。
        self.assertAlmostEqual(urgent["first_start"], 1.0)
        self.assertAlmostEqual(urgent["completion"], 5.0)
        self.assertEqual(urgent["preemptions"], 0)
        self.assertAlmostEqual(urgent["wait"], 0.0)
        # 被抢占普通票恰好一次抢占，剩余量 9 在 W1 急件完成后续办（W2 被另一普通票占用）。
        preempted = [r for r in by_ticket["NRM"] if r["preemptions"] == 1]
        self.assertEqual(len(preempted), 1)
        victim = preempted[0]
        # 服务段：[0,1) 与 [5,14)，完成时刻 14，等待累计 4（1->5）。
        self.assertAlmostEqual(victim["completion"], 14.0)
        self.assertAlmostEqual(victim["wait"], 4.0)
        self.assertEqual(out["overall"]["preemptions"], 1)
        self.assertTrue(out["conservation"]["balanced"])
        self.assertAlmostEqual(out["conservation"]["demand_minus_served_minus_remaining"], 0.0)
        self.assertAlmostEqual(out["conservation"]["served_minus_window_busy"], 0.0)

    def test_preempted_job_moves_to_other_compatible_window(self):
        classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.4, "mean_service_minutes": 1.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.6, "mean_service_minutes": 1.0},
        ]
        windows = [
            {"code": "A", "allowed": ["U", "N"]},
            {"code": "B", "allowed": ["U", "N"]},
        ]
        # t=0：N1、N2 分占 A、B（两窗均通办，服务量10、3）；t=1 急件 U1 到达，无空窗，抢占 A 上的 N1。
        # N1 剩余9 进入等待；t=3 N2 完成空出 B，N1 即刻换到 B 续办，t=12 完成。
        arrivals = {"N": [0.0, 0.0], "U": [1.0]}
        services = {"N": [10.0, 3.0], "U": [2.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        n1 = next(r for r in out["records"] if r["ticket"] == "N" and r["preemptions"] == 1)
        # N1 被抢占后等待 1->3，再在 B 续办剩余9，完成时刻 3+9=12；先后使用 A、B 两窗。
        self.assertAlmostEqual(n1["wait"], 2.0)
        self.assertAlmostEqual(n1["completion"], 12.0)
        self.assertEqual(n1["windows_used"], [1, 2])
        u1 = next(r for r in out["records"] if r["ticket"] == "U")
        self.assertAlmostEqual(u1["first_start"], 1.0)
        self.assertAlmostEqual(u1["completion"], 3.0)
        self.assertTrue(out["conservation"]["balanced"])

    def test_preempted_normal_waits_then_resumes_with_full_remaining(self):
        classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.4, "mean_service_minutes": 1.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.6, "mean_service_minutes": 1.0},
        ]
        windows = [
            {"code": "A", "allowed": ["U", "N"]},
            {"code": "B", "allowed": ["U", "N"]},
        ]
        # 两普通票服务量均为10；U1 t=1 抢占 A 上 N1，U1 服务6 到 t=7；N1 在 t=7 回到 A 续办剩余9。
        arrivals = {"N": [0.0, 0.0], "U": [1.0]}
        services = {"N": [10.0, 10.0], "U": [6.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        n1 = next(r for r in out["records"] if r["ticket"] == "N" and r["preemptions"] == 1)
        self.assertEqual(n1["preemptions"], 1)
        self.assertAlmostEqual(n1["wait"], 6.0)           # 1->7 再等待
        self.assertAlmostEqual(n1["completion"], 16.0)    # 7 + 剩余9
        self.assertEqual(n1["windows_used"], [1, 1])
        # 服务量守恒：10 = 1（被抢前）+ 9（续办）。
        self.assertTrue(out["conservation"]["balanced"])

    def test_completion_before_arrival_at_same_time(self):
        classes, windows = self._basic_spec()
        # 普通票 t=0 开工、服务量 5，t=5 完成；急件 t=5 到达。
        # 同刻完成先于到达 -> 急件直接使用空窗，无抢占。
        arrivals = {"NRM": [0.0], "URG": [5.0]}
        services = {"NRM": [5.0], "URG": [3.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        urgent = [r for r in out["records"] if r["ticket"] == "URG"][0]
        normal = [r for r in out["records"] if r["ticket"] == "NRM"][0]
        self.assertEqual(normal["preemptions"], 0)
        self.assertAlmostEqual(urgent["first_start"], 5.0)
        self.assertAlmostEqual(urgent["wait"], 0.0)
        self.assertEqual(out["overall"]["preemptions"], 0)
        self.assertTrue(out["conservation"]["balanced"])

    def test_fcfs_within_same_level(self):
        classes = [
            {"code": "N", "level": NORMAL, "arrival_share": 1.0, "mean_service_minutes": 5.0},
        ]
        windows = [{"code": "W", "allowed": ["N"]}]
        arrivals = {"N": [0.0, 1.0, 2.0]}
        services = {"N": [4.0, 4.0, 4.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        starts = [r["first_start"] for r in out["records"]]
        self.assertEqual(starts, [0.0, 4.0, 8.0])
        waits = [r["wait"] for r in out["records"]]
        self.assertEqual(waits, [0.0, 3.0, 6.0])
        self.assertTrue(out["conservation"]["balanced"])

    def test_urgent_allocation_maximized_then_total(self):
        classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.34, "mean_service_minutes": 1.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.66, "mean_service_minutes": 1.0},
        ]
        windows = [{"code": "W1", "allowed": ["U", "N"]}, {"code": "W2", "allowed": ["U", "N"]}]
        arrivals = {"U": [0.0], "N": [0.0, 0.0]}
        services = {"U": [5.0], "N": [5.0, 5.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        u = [r for r in out["records"] if r["ticket"] == "U"][0]
        self.assertAlmostEqual(u["first_start"], 0.0)  # 急件先开工
        # 急件占一窗后，再让一张普通票开工（总开工最大化），另一普通票等待。
        n_starts = sorted(r["first_start"] for r in out["records"] if r["ticket"] == "N")
        self.assertEqual(n_starts[0], 0.0)
        self.assertGreater(n_starts[1], 0.0)
        self.assertTrue(out["conservation"]["balanced"])

    def test_matching_prefers_constrained_window_to_maximize_urgent_starts(self):
        # UA 只能在专办窗 W-SPEC 办；UB 可在 W-SPEC 或通办窗 W-ALL 办。
        # 朴素逐窗 FCFS 会把先到的 UB 放进 W-SPEC，导致 UA 无窗；正确匹配应让 UA 进 W-SPEC、UB 进 W-ALL，
        # 使两张急件同时开工（急件开工数最大）。
        classes = [
            {"code": "UA", "level": URGENT, "arrival_share": 0.5, "mean_service_minutes": 1.0},
            {"code": "UB", "level": URGENT, "arrival_share": 0.5, "mean_service_minutes": 1.0},
        ]
        windows = [
            {"code": "W-SPEC", "allowed": ["UA"]},
            {"code": "W-ALL", "allowed": ["UA", "UB"]},
        ]
        # UB 到达更早（t=0），UA 稍后同批到达（t=0，靠 seq 决胜），但匹配仍须两张都开工。
        arrivals = {"UB": [0.0], "UA": [0.0]}
        services = {"UB": [4.0], "UA": [4.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        starts = {r["ticket"]: r["first_start"] for r in out["records"]}
        self.assertAlmostEqual(starts["UA"], 0.0)
        self.assertAlmostEqual(starts["UB"], 0.0)  # 两张急件都在 t=0 开工
        win_of = {r["ticket"]: r["window"] for r in out["records"]}
        self.assertEqual(win_of["UA"], 1)  # 专办窗留给唯一能使用它的 UA
        self.assertEqual(win_of["UB"], 2)
        self.assertTrue(out["conservation"]["balanced"])

    def test_window_compatibility_blocks_incompatible_ticket(self):
        classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.5, "mean_service_minutes": 1.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.5, "mean_service_minutes": 1.0},
        ]
        windows = [{"code": "only-N", "allowed": ["N"]}, {"code": "both", "allowed": ["U", "N"]}]
        # N 占满两窗，急件只能抢占 both 窗；only-N 上的普通票不应被碰。
        arrivals = {"N": [0.0, 0.0], "U": [2.0]}
        services = {"N": [8.0, 8.0], "U": [2.0]}
        out = schedule_priority(classes, windows, arrivals, services)
        victim = [r for r in out["records"] if r["preemptions"] == 1][0]
        self.assertEqual(victim["windows_used"][0], 2)  # 被抢的是 both(2号窗)
        untouched = [r for r in out["records"] if r["ticket"] == "N" and r["preemptions"] == 0][0]
        self.assertEqual(untouched["windows_used"], [1])
        self.assertTrue(out["conservation"]["balanced"])

    def test_warmup_excludes_early_jobs_from_stats_but_keeps_state(self):
        classes, windows = self._basic_spec()
        arrivals = {"NRM": [0.0, 0.0, 0.0], "URG": [10.0]}
        services = {"NRM": [5.0, 5.0, 5.0], "URG": [2.0]}
        out = schedule_priority(classes, windows, arrivals, services, warmup=3)
        self.assertEqual(out["overall"]["retained"], 1)
        self.assertEqual(sum(c["retained"] for c in out["per_ticket"]), 1)
        # 暖机票仍完成，守恒按全部票核对。
        self.assertTrue(out["conservation"]["balanced"])
        self.assertEqual(out["overall"]["completed"], 1)

    def test_stochastic_run_conservation_and_determinism(self):
        rng = random.Random(20261115)
        # 两窗均为通办窗口，高负荷下急件到达时窗口常被普通票占用，抢占必然发生。
        classes, _ = self._basic_spec()
        windows = [
            {"code": "W1", "allowed": ["URG", "NRM"]},
            {"code": "W2", "allowed": ["URG", "NRM"]},
        ]
        n = 800
        arrivals = {"URG": [], "NRM": []}
        services = {"URG": [], "NRM": []}
        t = 0.0
        for _ in range(n):
            t += rng.expovariate(0.9)  # 总到达率，刻意制造争用
            code = "URG" if rng.random() < 0.4 else "NRM"
            mean = 4.0 if code == "URG" else 6.0
            arrivals[code].append(t)
            services[code].append(rng.expovariate(1 / mean))
        out1 = schedule_priority(classes, windows, arrivals, services, warmup=50)
        out2 = schedule_priority(classes, windows, arrivals, services, warmup=50)
        self.assertEqual(
            [(r["seq"], r["completion"], r["wait"]) for r in out1["records"]],
            [(r["seq"], r["completion"], r["wait"]) for r in out2["records"]],
        )
        self.assertTrue(out1["conservation"]["balanced"])
        # 所有票均完成；急件平均等待显著低于普通票（抢占生效的经验性核对）。
        urg = next(c for c in out1["per_ticket"] if c["ticket"] == "URG")
        nrm = next(c for c in out1["per_ticket"] if c["ticket"] == "NRM")
        self.assertEqual(urg["completed"] + nrm["completed"], n - 50)
        self.assertGreater(nrm["preemptions"], 0)
        self.assertLess(urg["mean_wait_minutes"], nrm["mean_wait_minutes"])
        # 每票种：到达数 = 完成数（全部），抢占次数非负。
        for c in out1["per_ticket"]:
            self.assertGreaterEqual(c["preemptions"], 0)
            self.assertAlmostEqual(
                c["total_service_demand_minutes"],
                c["served_minutes"] + c["remaining_minutes"], places=9)

    def test_validation_errors(self):
        good_classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.4, "mean_service_minutes": 2.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.6, "mean_service_minutes": 3.0},
        ]
        with self.assertRaises(ValueError):
            schedule_priority([{**good_classes[0], "arrival_share": 0.5}],
                              [{"code": "W", "allowed": ["U"]}],
                              {"U": [0.0]}, {"U": [1.0]})  # 占比和≠1
        with self.assertRaises(ValueError):
            schedule_priority(good_classes, [{"code": "W", "allowed": ["U"]}],
                              {"U": [0.0], "N": [1.0]}, {"U": [1.0], "N": [1.0]})  # N 无可办窗
        with self.assertRaises(ValueError):
            schedule_priority(good_classes, [{"code": "W", "allowed": ["X"]}],
                              {"U": [0.0], "N": [1.0]}, {"U": [1.0], "N": [1.0]})  # 未知票种


if __name__ == "__main__":
    unittest.main()
