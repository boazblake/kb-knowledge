import unittest

from kb_pipeline.benchmark import (SLODefaults, Summary, compare_slos, error_budget, percentile,
                                   run_harness, summarize)


class BenchmarkMathTests(unittest.TestCase):
    def test_percentiles_are_deterministic(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2, 3, 4], 95), 3.85)
        self.assertEqual(percentile([], 99), 0.0)

    def test_summary_counts_errors_and_throughput(self):
        result = summarize([10, 20, 30, 40], 1, 2.0)
        self.assertEqual(result.count, 5)
        self.assertEqual(result.errors, 1)
        self.assertEqual(result.p50_ms, 25.0)
        self.assertEqual(result.throughput_per_second, 2.5)
        self.assertEqual(result.error_rate, 0.2)

    def test_error_budget_burn(self):
        result = error_budget(0.999, 0.005)
        self.assertEqual(result["budget_fraction"], 0.001)
        self.assertEqual(result["burn_rate"], 5.0)
        self.assertFalse(result["within_budget"])
        self.assertTrue(result["burn_alerts"]["fast_1h"])
        self.assertTrue(result["burn_alerts"]["slow_6h"])
        self.assertEqual(result["budget_minutes_30d"], 43.2)

    def test_slo_comparison_includes_freshness_purge_and_authority(self):
        good = Summary(100, 0, 1, 10, 20, 200, 0)
        result = compare_slos(good, good, freshness_seconds=10, purge_seconds=10,
                              dependency_checks={"authority_fresh": False, "freshness_dependency": True})
        self.assertTrue(result["checks"]["search_p95"])
        self.assertTrue(result["checks"]["freshness"])
        self.assertTrue(result["checks"]["purge_sla"])
        self.assertFalse(result["checks"]["authority_dependencies"])

    def test_harness_is_fail_closed_and_labels_local_result(self):
        result = run_harness(records=4, searches=6, concurrency=2, warmup=1)
        self.assertEqual(result["result_class"], "synthetic-local-simulated")
        self.assertEqual(result["qualification"], "not_production_qualification")
        self.assertEqual(result["readiness"], "not_ready")
        self.assertFalse(result["slo_comparison"]["checks"]["authority_dependencies"])
        self.assertEqual(result["evidence_manifest"]["topology"]["backend"], "SQLite FTS5")


if __name__ == "__main__":
    unittest.main()
