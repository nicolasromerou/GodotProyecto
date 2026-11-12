#!/usr/bin/env python3
"""Focused tests for the local traffic-priority planner."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tools.traffic_coordinator import plan

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "traffic_coordinator.py")


def junction(identifier, counts=None, queues=None, wait=None, downstream=None, **extra):
    return {
        "id": identifier,
        "counts": counts or [0, 0, 0, 0],
        "queues": queues or [0, 0, 0, 0],
        "wait": wait or [0, 0, 0, 0],
        "downstream_queues": downstream or [0, 0, 0, 0],
        "sensors_online": True,
        "fallback": False,
        **extra,
    }


class TrafficCoordinatorTests(unittest.TestCase):
    def network(self, first, **overrides):
        junctions = [first] + [junction(index) for index in range(2, 10)]
        if overrides:
            junctions[0].update(overrides)
        return {"junctions": junctions}

    def test_selects_axis_with_larger_stopped_queue(self):
        result = plan(self.network(junction(1, queues=[1, 4, 0, 0])))
        self.assertEqual(result["decisions"][0]["priority"], "EW")

    def test_waiting_time_prevents_starvation(self):
        result = plan(self.network(junction(1, counts=[2, 2, 0, 0], wait=[0, 30, 0, 0])))
        self.assertEqual(result["decisions"][0]["priority"], "EW")

    def test_avoids_downstream_gridlock_when_alternative_exists(self):
        result = plan(self.network(junction(1, queues=[3, 2, 0, 0], downstream=[0, 5, 0, 0])))
        self.assertEqual(result["decisions"][0]["priority"], "NS")

    def test_keeps_previous_axis_when_scores_are_close(self):
        result = plan(self.network(junction(1, counts=[2, 2.1, 0, 0], previous_axis="NS")))
        self.assertEqual(result["decisions"][0]["priority"], "NS")

    def test_empty_or_unhealthy_cross_does_not_receive_priority(self):
        data = self.network(junction(1))
        data["junctions"][1]["sensors_online"] = False
        decisions = plan(data)["decisions"]
        self.assertEqual(decisions[0]["priority"], "")
        self.assertEqual(decisions[1]["priority"], "")

    def test_rejects_malformed_or_unsafe_input(self):
        with self.assertRaises(ValueError):
            plan([])
        with self.assertRaises(ValueError):
            plan({"junctions": []})
        with self.assertRaises(ValueError):
            plan(self.network(junction(1, counts=[float("nan"), 0, 0, 0])))
        duplicate = self.network(junction(1))
        duplicate["junctions"][1]["id"] = 1
        with self.assertRaises(ValueError):
            plan(duplicate)
        with self.assertRaises(ValueError):
            plan(self.network(junction(1, previous_axis=[])))


    def test_reads_input_file_as_godot_sends_it(self):
        # Es el camino que usa la demo: la instantánea va en un archivo UTF-8.
        payload = self.network(junction(1, queues=[3, 0, 3, 0]))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "entrada.json")
            with open(path, "w", encoding="utf-8") as archivo:
                json.dump(payload, archivo)
            result = subprocess.run([sys.executable, SCRIPT, "--input-file", path], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        decisions = json.loads(result.stdout)["decisions"]
        self.assertEqual(len(decisions), 9)
        self.assertEqual(decisions[0]["priority"], "NS")

    def test_missing_input_file_is_reported(self):
        result = subprocess.run([sys.executable, SCRIPT, "--input-file", os.path.join(tempfile.gettempdir(), "no-existe-fti.json")], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
