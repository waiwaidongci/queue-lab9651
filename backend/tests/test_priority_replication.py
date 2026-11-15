"""独立重复层、按票种报告口径与同刻次序的纯标准库核对。"""
import unittest

from src.services.priority_algorithm import schedule_priority, URGENT, NORMAL
from src.services.priority_simulation import (
    simulate_priority_replicates, mean_t_interval, _t_ppf,
)


def two_class_spec():
    classes = [
        {"code": "URG", "level": URGENT, "arrival_share": 0.3, "mean_service_minutes": 3.0},
        {"code": "NRM", "level": NORMAL, "arrival_share": 0.7, "mean_service_minutes": 5.0},
    ]
    windows = [
        {"code": "W1", "allowed": ["URG", "NRM"]},
        {"code": "W2", "allowed": ["NRM"]},
    ]
    return classes, windows


class ReplicationReportingTests(unittest.TestCase):
    def test_per_ticket_report_fields_and_conservation(self):
        classes, windows = two_class_spec()
        out = simulate_priority_replicates(
            classes, windows, total_arrival_rate=0.6,
            customers=800, warmup=100, replications=5, seed=4242)
        self.assertEqual(out["mode"], "multi_class_preemptive_priority")
        self.assertIsNone(out["analytical"])  # 无适用解析值时显式为 null
        self.assertIn("不存在", out["analytical_note"])
        tickets = {c["ticket"]: c for c in out["per_ticket_summary"]}
        self.assertEqual(set(tickets), {"URG", "NRM"})
        for code, c in tickets.items():
            # 报告契约：累计等待、抢占次数、完成数均存在且口径自洽。
            self.assertIn("cumulative_wait_minutes", c)
            self.assertIn("preemptions", c)
            self.assertIn("mean_completed", c)
            self.assertGreaterEqual(c["preemptions"], 0)
            self.assertGreater(c["mean_completed"], 0)
            # 急件不会成为被抢占对象（只有普通票被抢）。
            if code == "URG":
                self.assertEqual(c["preemptions"], 0)
        # 完成数跨票种之和等于保留票数。
        retained_total = sum(c["mean_completed"] for c in tickets.values())
        self.assertAlmostEqual(retained_total, 800 - 100, places=6)
        # 服务量守恒在所有重复上通过。
        self.assertTrue(out["conservation"]["all_replications_balanced"])
        self.assertEqual(out["conservation"]["max_abs_demand_gap"], 0.0)
        self.assertLess(out["conservation"]["max_abs_busy_gap"], 1e-9)
        # 每条重复都带守恒块和 spawn 键。
        for rep in out["replications"]:
            self.assertTrue(rep["conservation"]["balanced"])
            self.assertEqual(len(rep["arrival_spawn_key"]), 3)
            self.assertEqual(len(rep["service_spawn_key"]), 3)

    def test_replication_determinism_and_independence(self):
        classes, windows = two_class_spec()
        a = simulate_priority_replicates(classes, windows, 0.6, 800, 100, 6, 2026)
        b = simulate_priority_replicates(classes, windows, 0.6, 800, 100, 6, 2026)
        self.assertEqual(
            [r["overall"]["mean_wait_minutes"] for r in a["replications"]],
            [r["overall"]["mean_wait_minutes"] for r in b["replications"]])
        c = simulate_priority_replicates(classes, windows, 0.6, 800, 100, 6, 2027)
        self.assertNotEqual(
            [r["overall"]["mean_wait_minutes"] for r in a["replications"]],
            [r["overall"]["mean_wait_minutes"] for r in c["replications"]])
        # 同种子不同重复号的派生流不同 -> 重复间不是同一份随机序列。
        keys = {tuple(r["arrival_spawn_key"]) for r in a["replications"]}
        self.assertEqual(len(keys), 6)

    def test_same_time_arrival_urgent_before_normal(self):
        # 单窗、同刻到达一张急件和一张普通票：急件先开工，普通票等待。
        classes = [
            {"code": "U", "level": URGENT, "arrival_share": 0.5, "mean_service_minutes": 1.0},
            {"code": "N", "level": NORMAL, "arrival_share": 0.5, "mean_service_minutes": 1.0},
        ]
        windows = [{"code": "W", "allowed": ["U", "N"]}]
        out = schedule_priority(
            classes, windows,
            {"U": [0.0], "N": [0.0]}, {"U": [3.0], "N": [3.0]})
        u = next(r for r in out["records"] if r["ticket"] == "U")
        n = next(r for r in out["records"] if r["ticket"] == "N")
        self.assertAlmostEqual(u["first_start"], 0.0)
        self.assertAlmostEqual(u["completion"], 3.0)
        self.assertAlmostEqual(n["first_start"], 3.0)
        self.assertAlmostEqual(n["wait"], 3.0)
        self.assertTrue(out["conservation"]["balanced"])

    def test_guard_rails(self):
        classes, windows = two_class_spec()
        with self.assertRaises(ValueError):
            simulate_priority_replicates(classes, windows, 0.6, 100, 0, 5, 1)  # 顾客 < 500
        with self.assertRaises(ValueError):
            simulate_priority_replicates(classes, windows, 0.6, 500, 450, 5, 1)  # 保留 < 100
        with self.assertRaises(ValueError):
            simulate_priority_replicates(classes, windows, 0.6, 500, 0, 3, 1)    # 重复 < 5
        with self.assertRaises(ValueError):
            simulate_priority_replicates(classes, windows, 0.6, 500, 0, 5, -1)   # 种子越界

    def test_t_interval_matches_known_critical(self):
        iv = mean_t_interval([2.0, 4.0, 6.0], 0.95)
        self.assertEqual(iv["degrees_of_freedom"], 2)
        self.assertAlmostEqual(iv["critical_t"], _t_ppf(0.975, 2), places=9)
        self.assertAlmostEqual(iv["mean"], 4.0)
        self.assertFalse(iv["degenerate"])
        deg = mean_t_interval([3.0, 3.0, 3.0], 0.95)
        self.assertTrue(deg["degenerate"])

    def test_cumulative_wait_is_sum_of_individual_waits(self):
        classes, windows = two_class_spec()
        out = schedule_priority(
            classes, windows,
            {"URG": [1.0, 5.0], "NRM": [0.0, 0.0, 6.0]},
            {"URG": [2.0, 2.0], "NRM": [6.0, 6.0, 4.0]}, warmup=0)
        for c in out["per_ticket"]:
            members = [r for r in out["records"] if r["ticket"] == c["ticket"]]
            self.assertAlmostEqual(
                c["cumulative_wait_minutes"], sum(m["wait"] for m in members), places=9)
            self.assertEqual(c["completed"], len(members))
        self.assertTrue(out["conservation"]["balanced"])


if __name__ == "__main__":
    unittest.main()
