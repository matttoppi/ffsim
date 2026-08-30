import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ffsim.api import LiveDraftMonitor


class Telemetry:
    def __init__(self, fail=False):
        self.fail = fail
        self.records = []
        self.event = threading.Event()

    def record(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("telemetry unavailable")
        self.records.append((args, kwargs))
        self.event.set()


class Collector:
    def __init__(self, result=None, error=None, wait=None):
        self.result = result or {"status": "ready", "manager_replay_input": {}}
        self.error = error
        self.wait = wait
        self.called = threading.Event()

    def collect(self, prepared, state, recommendation):
        self.called.set()
        if self.wait is not None:
            self.wait.wait(2)
        if self.error is not None:
            raise self.error
        return self.result


class AlphaShadowMonitorTest(unittest.TestCase):
    def monitor(self, collector, telemetry=None):
        monitor = LiveDraftMonitor(
            SimpleNamespace(live_draft_id="draft"),
            1.0,
            300,
            9,
            telemetry=telemetry,
            alpha_shadow_collector=collector,
            alpha_shadow_status="idle",
        )
        monitor.state_fingerprint = ("state",)
        return monitor

    def test_shadow_publishes_state_and_telemetry_without_changing_monitor(self):
        telemetry = Telemetry()
        collector = Collector({
            "status": "ready",
            "decision_active": False,
            "manager_replay_input": {"candidate_ids": ["p1", "p2"]},
        })
        monitor = self.monitor(collector, telemetry)

        monitor._queue_alpha_shadow(
            ("state",), 10, SimpleNamespace(), {"recommended_candidate_id": "p1"}
        )

        self.assertTrue(telemetry.event.wait(2))
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["alpha_shadow_status"], "ready")
        self.assertEqual(snapshot["alpha_shadow_pick_no"], 10)
        self.assertFalse(snapshot["alpha_shadow"]["decision_active"])
        self.assertEqual(snapshot["alpha_shadow_calculation_count"], 1)
        self.assertEqual(telemetry.records[0][0][2], "alpha_shadow")
        self.assertEqual(monitor.status, "starting")

    def test_shadow_failure_and_telemetry_failure_cannot_fail_monitor(self):
        telemetry = Telemetry(fail=True)
        collector = Collector(error=RuntimeError("shadow failed"))
        monitor = self.monitor(collector, telemetry)

        with patch("ffsim.api.LOGGER"):
            monitor._queue_alpha_shadow(
                ("state",),
                10,
                SimpleNamespace(),
                {"recommended_candidate_id": "p1"},
            )
            self.assertTrue(collector.called.wait(2))
            for _ in range(100):
                if monitor.snapshot()["alpha_shadow_status"] == "failed":
                    break
                threading.Event().wait(0.01)
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["alpha_shadow_status"], "failed")
        self.assertEqual(snapshot["alpha_shadow_error"], "shadow failed")
        self.assertEqual(monitor.status, "starting")
        self.assertFalse(monitor.stopped.is_set())

    def test_stale_shadow_result_is_discarded(self):
        release = threading.Event()
        telemetry = Telemetry()
        collector = Collector(wait=release)
        monitor = self.monitor(collector, telemetry)
        monitor._queue_alpha_shadow(
            ("state",), 10, SimpleNamespace(), {"recommended_candidate_id": "p1"}
        )
        self.assertTrue(collector.called.wait(2))
        with monitor.lock:
            monitor.state_fingerprint = ("new-state",)
            monitor.alpha_shadow_status = "stale"
        release.set()

        self.assertTrue(telemetry.event.wait(2))
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot["alpha_shadow_status"], "stale")
        self.assertIsNone(snapshot["alpha_shadow"])
        self.assertEqual(telemetry.records[0][0][2], "alpha_shadow_discarded")

    def test_newest_shadow_state_queues_without_overlapping_workers(self):
        release = threading.Event()

        class SerialCollector(Collector):
            def __init__(self):
                super().__init__()
                self.active = 0
                self.max_active = 0
                self.calls = 0
                self.lock = threading.Lock()

            def collect(self, prepared, state, recommendation):
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                    self.calls += 1
                    call = self.calls
                try:
                    self.called.set()
                    if call == 1:
                        release.wait(2)
                    return {
                        "status": "ready",
                        "pick": recommendation["pick"],
                    }
                finally:
                    with self.lock:
                        self.active -= 1

        telemetry = Telemetry()
        collector = SerialCollector()
        monitor = self.monitor(collector, telemetry)
        monitor._queue_alpha_shadow(
            ("state",), 10, SimpleNamespace(), {"pick": 10}
        )
        self.assertTrue(collector.called.wait(2))
        with monitor.lock:
            monitor.state_fingerprint = ("new-state",)
        monitor._queue_alpha_shadow(
            ("new-state",), 11, SimpleNamespace(), {"pick": 11}
        )
        release.set()
        for _ in range(200):
            snapshot = monitor.snapshot()
            if (
                snapshot["alpha_shadow_status"] == "ready"
                and snapshot["alpha_shadow_pick_no"] == 11
            ):
                break
            threading.Event().wait(0.01)

        snapshot = monitor.snapshot()
        self.assertEqual(collector.calls, 2)
        self.assertEqual(collector.max_active, 1)
        self.assertEqual(snapshot["alpha_shadow"]["pick"], 11)
        self.assertEqual(snapshot["alpha_shadow_calculation_count"], 1)
        self.assertEqual(
            [record[0][2] for record in telemetry.records],
            ["alpha_shadow_discarded", "alpha_shadow"],
        )


if __name__ == "__main__":
    unittest.main()
