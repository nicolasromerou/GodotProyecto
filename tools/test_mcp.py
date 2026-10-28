"""Tests for the actual MCP stdio process; --integration also launches Godot."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import mcp_server

HERE = Path(__file__).resolve().parent
INTEGRATION = False


def exchange(messages):
    data = "".join(json.dumps(item) + "\n" for item in messages)
    result = subprocess.run([sys.executable, str(HERE / "mcp_server.py")], input=data,
                            text=True, encoding="utf-8", capture_output=True, timeout=360)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [json.loads(line) for line in result.stdout.splitlines()]


def initialized():
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]


class MCPTests(unittest.TestCase):
    def test_handshake_ping_tools(self):
        replies = exchange(initialized() + [
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ])
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(replies[1]["result"], {})
        self.assertEqual({tool["name"] for tool in replies[2]["result"]["tools"]},
                         {"fti_project_info", "fti_validate", "fti_run_tests", "fti_simulate"})

    def test_initialization_required(self):
        reply = exchange([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])[0]
        self.assertEqual(reply["error"]["code"], -32002)

    def test_invalid_tools_and_arguments(self):
        cases = [("not_a_tool", {}), ("fti_simulate", {"mode": "unknown"}),
                 ("fti_simulate", {"seconds": -1}), ("fti_simulate", {"seconds": 121}),
                 ("fti_simulate", {"seconds": True}), ("fti_simulate", {"sensor_enabled": "false"}),
                 ("fti_simulate", {"mode": ["fti"]}), ("fti_validate", {"script": "../../bad"})]
        messages = initialized() + [{"jsonrpc": "2.0", "id": index + 2, "method": "tools/call", "params": {"name": name, "arguments": args}} for index, (name, args) in enumerate(cases)]
        replies = exchange(messages)[1:]
        self.assertEqual(len(replies), len(cases))
        for reply in replies:
            self.assertEqual(reply["error"]["code"], -32602)

    def test_project_info(self):
        reply = exchange(initialized() + [{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "fti_project_info", "arguments": {}}}])[-1]
        self.assertFalse(reply["result"]["isError"])
        info = json.loads(reply["result"]["content"][0]["text"])
        self.assertFalse(info["live_editor_control"])
        self.assertFalse(info["models_included"])
        self.assertEqual(Path(info["project"]), HERE.parent)

    def test_godot_integration(self):
        if not INTEGRATION:
            self.skipTest("Use --integration para ejecutar Godot")
        requests = [("fti_validate", {}), ("fti_run_tests", {}),
                    ("fti_simulate", {"mode": "adaptive", "seconds": 30}),
                    ("fti_simulate", {"mode": "fti", "seconds": 12, "sensor_enabled": False})]
        replies = exchange(initialized() + [{"jsonrpc": "2.0", "id": i + 2, "method": "tools/call", "params": {"name": name, "arguments": args}} for i, (name, args) in enumerate(requests)])[1:]
        for reply in replies:
            self.assertFalse(reply["result"]["isError"], reply)
            self.assertTrue(json.loads(reply["result"]["content"][0]["text"])["ok"])
        snapshot = json.loads(replies[-1]["result"]["content"][0]["text"])["snapshot"]
        self.assertIsInstance(snapshot, dict)
        self.assertTrue(snapshot["controller"]["fallback"])
        self.assertEqual(snapshot["controller"]["running_mode"], "fixed")


class GodotRunnerTests(unittest.TestCase):
    """Exercise process diagnostics without requiring an installed engine."""

    @staticmethod
    def fake_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        def run(command, **kwargs):
            kwargs["stdout"].write(stdout)
            kwargs["stderr"].write(stderr)
            return subprocess.CompletedProcess(command, returncode)
        return run

    def test_error_in_clipped_middle_of_either_stream_still_fails(self):
        padding = b"engine output\n" * 1200
        payload = padding + b"ERROR: GDScript test failure\n" + padding
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream), mock.patch.object(
                    mcp_server.subprocess, "run", side_effect=self.fake_process(**{stream: payload})):
                result = mcp_server.run_godot(Path("fake-godot"), ["--editor", "--import"])
            self.assertFalse(result["ok"])
            self.assertIn("[output truncated]", result[stream])
            self.assertNotIn("GDScript test failure", result[stream])

    def test_missing_or_failed_completion_marker_is_rejected(self):
        pattern = mcp_server.TEST_COMPLETIONS[mcp_server.TEST_SCRIPTS[0]]
        for line in (b"Godot exited without running tests\n",
                     b"Controller: 36 checks; 1 failures\n",
                     b"Controller: 0 checks; 0 failures\n"):
            with self.subTest(output=line), mock.patch.object(
                    mcp_server.subprocess, "run", side_effect=self.fake_process(stdout=line)):
                result = mcp_server.run_godot(Path("fake-godot"), ["--script", "test.gd"],
                                               completion_pattern=pattern)
            self.assertFalse(result["ok"])
            self.assertIsNone(result["completion_marker"])
            self.assertIn("marcador", result["error"])

    def test_completion_marker_in_clipped_middle_is_accepted(self):
        padding = b"engine output\n" * 1200
        for script, marker in ((mcp_server.TEST_SCRIPTS[0], b"Controller: 36 checks; 0 failures"),
                               (mcp_server.TEST_SCRIPTS[1], b"WORLD_TESTS 20 passed, 0 failed")):
            payload = padding + marker + b"\n" + padding
            with self.subTest(script=script), mock.patch.object(
                    mcp_server.subprocess, "run", side_effect=self.fake_process(stdout=payload)):
                result = mcp_server.run_godot(Path("fake-godot"), ["--script", script],
                                               completion_pattern=mcp_server.TEST_COMPLETIONS[script])
            self.assertTrue(result["ok"])
            self.assertEqual(result["completion_marker"], marker.decode())
            self.assertNotIn(marker.decode(), result["stdout"])

    def test_only_exact_certificate_warning_is_ignored(self):
        for line, expected in ((b"ERROR: Failed to read the root certificate store.\n", True),
                               (b"ERROR: Failed to read the root certificate store. Other error\n", False)):
            with self.subTest(output=line), mock.patch.object(
                    mcp_server.subprocess, "run", side_effect=self.fake_process(stderr=line)):
                result = mcp_server.run_godot(Path("fake-godot"), [])
            self.assertEqual(result["ok"], expected)
            self.assertEqual(bool(result["environment_warning"]), expected)

    def test_test_tool_requires_each_suite_completion(self):
        with mock.patch.object(mcp_server, "run_godot", return_value={"ok": True}) as runner:
            result = mcp_server.call_tool("fti_run_tests", {}, Path("fake-godot"))
        self.assertTrue(result["ok"])
        self.assertEqual(runner.call_count, 2)
        for call, script in zip(runner.call_args_list, mcp_server.TEST_SCRIPTS):
            self.assertEqual(call.kwargs["completion_pattern"], mcp_server.TEST_COMPLETIONS[script])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true")
    args, remaining = parser.parse_known_args()
    INTEGRATION = args.integration
    unittest.main(argv=[sys.argv[0], *remaining])
