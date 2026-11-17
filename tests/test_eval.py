"""Assignment 7, Part B: the tests the harness's maths and metrics must pass (slides 10,
18, 19, 20 and 27 of Lecture 7). `make test` runs them; they spend no tokens."""

from __future__ import annotations

import json
import unittest

from harness import ROOT
from harness.tasks import load_task
from eval import stats
from eval.metrics import metrics

OLD = [61.0, 63.5, 59.5, 62.0, 64.5, 61.5, 62.5, 60.5, 63.0, 62.0]
NEW = [63.5, 65.0, 62.5, 66.0, 64.5, 67.5, 65.0, 64.0, 66.5, 65.5]


class PassMetrics(unittest.TestCase):
    """Slide 10: n = 8 runs, c = 6 passes."""

    def test_pass_at_2(self):
        self.assertAlmostEqual(stats.pass_at_k(8, 6, 2), 0.96, places=2)

    def test_pass_hat_2(self):
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 2), 0.54, places=2)

    def test_pass_hat_4(self):
        self.assertAlmostEqual(stats.pass_hat_k(8, 6, 4), 0.21, places=2)

    def test_pass_hat_is_not_pass1_to_the_k(self):
        # pass@1 ** 4 = 0.75 ** 4 = 0.32, the biased shortcut; counting gives 0.21.
        self.assertNotAlmostEqual(stats.pass_hat_k(8, 6, 4), (6 / 8) ** 4, places=2)

    def test_edges(self):
        self.assertEqual(stats.pass_at_k(5, 5, 5), 1.0)
        self.assertEqual(stats.pass_at_k(5, 0, 3), 0.0)
        self.assertEqual(stats.pass_hat_k(5, 2, 3), 0.0)

    def test_over_tasks(self):
        at, hat = stats.over_tasks({"a": (5, 3), "b": (5, 5), "c": (5, 0)}, 2)
        self.assertAlmostEqual(at, (0.9 + 1.0 + 0.0) / 3)
        self.assertAlmostEqual(hat, (0.3 + 1.0 + 0.0) / 3)


class SpreadAndInterval(unittest.TestCase):
    """Slides 18 to 20."""

    def test_slide_18_averages_and_spread(self):
        self.assertAlmostEqual(sum(OLD) / len(OLD), 62.0)
        self.assertAlmostEqual(sum(NEW) / len(NEW), 65.0)
        self.assertAlmostEqual(stats.spread(OLD), 1.47, places=2)
        self.assertAlmostEqual(stats.spread(NEW), 1.47, places=2)
        gain, low, high = stats.interval(NEW, OLD)
        self.assertAlmostEqual(gain, 3.0)
        self.assertLess(low, gain)
        self.assertGreater(high, gain)

    def test_spread_of_one_value(self):
        self.assertEqual(stats.spread([4.0]), 0.0)

    def test_slide_19_margin(self):
        m = stats.margin(1.5, 10, 1.5, 10)
        self.assertAlmostEqual(m, 1.31, places=2)
        self.assertAlmostEqual(3 - m, 1.69, places=2)
        self.assertAlmostEqual(3 + m, 4.31, places=2)

    def test_slide_20_wide_spread(self):
        m = stats.margin(6.0, 10, 6.0, 10)
        self.assertAlmostEqual(3 - m, -2.3, places=1)
        self.assertAlmostEqual(3 + m, 8.3, places=1)

    def test_sweeps_needed(self):
        # Activity 2: s = 1.5 for both arms and delta = 3 gives about four.
        self.assertEqual(stats.sweeps_needed(1.5, 1.5, 3), 4)
        self.assertEqual(stats.sweeps_needed(0.0, 0.0, 3), 1)


class Slide27(unittest.TestCase):
    """Slide 27's trace: seven calls against a four-call reference."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "fixtures" / "traces7" / "s27.jsonl"
        cls.lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        cls.task = load_task(ROOT / "fixtures" / "traces7" / "s27.task.yaml")
        cls.got = metrics(cls.lines, cls.task)

    def test_step_count(self):
        self.assertEqual(self.got["step_count"], 3)

    def test_precision(self):
        self.assertAlmostEqual(self.got["precision"], 4 / 5)

    def test_recall(self):
        self.assertAlmostEqual(self.got["recall"], 4 / 4)

    def test_repeats(self):
        self.assertEqual(self.got["repeats"], 1)

    def test_orphans(self):
        self.assertEqual(self.got["orphans"], 1)

    def test_tools_called_and_cost(self):
        self.assertFalse(self.got["no_tools"])
        self.assertAlmostEqual(self.got["cost_usd"], 0.0198)
        self.assertAlmostEqual(self.got["latency_s"], 21.4)


if __name__ == "__main__":
    unittest.main()
