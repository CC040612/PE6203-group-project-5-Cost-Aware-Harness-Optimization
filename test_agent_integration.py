import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from harbor.agents.terminus_2.terminus_2 import Terminus2
from member3.loop_recovery import LoopRecoveryTerminus2


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.logs_dir = Path(self.temp.name)
        self.commands = [SimpleNamespace(keystrokes="missing_tool\n")]
        self.output = "missing_tool: command not found"

    def make_agent(self, enabled=True):
        # Skip model initialization: these tests need no API or credentials.
        with patch.object(Terminus2, "__init__", return_value=None):
            agent = LoopRecoveryTerminus2(
                logs_dir=self.logs_dir,
                enable_loop_recovery=enabled,
            )
        agent._n_episodes = 3
        return agent

    async def test_third_failure_adds_notice_and_writes_event(self):
        agent = self.make_agent()
        with patch.object(
            Terminus2,
            "_execute_commands",
            new_callable=AsyncMock,
            return_value=(False, self.output),
        ) as execute:
            for _ in range(2):
                result = await agent._execute_commands(self.commands, None)
                self.assertEqual(result, (False, self.output))

            timeout, output = await agent._execute_commands(
                self.commands, None
            )

        self.assertFalse(timeout)
        self.assertIn("[Harness recovery notice]", output)
        self.assertTrue(output.endswith(self.output))
        self.assertEqual(execute.await_count, 3)

        lines = (self.logs_dir / "loop_recovery_events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event["repeat_count"], 3)
        self.assertEqual(event["command"], "missing_tool\n")

    async def test_disabled_preserves_original_result(self):
        agent = self.make_agent(enabled="false")
        with patch.object(
            Terminus2,
            "_execute_commands",
            new_callable=AsyncMock,
            return_value=(False, self.output),
        ):
            for _ in range(4):
                result = await agent._execute_commands(self.commands, None)
                self.assertEqual(result, (False, self.output))

        self.assertFalse(
            (self.logs_dir / "loop_recovery_events.jsonl").exists()
        )

    async def test_completion_is_not_modified(self):
        agent = self.make_agent()
        agent._completion_requested = True
        with patch.object(
            Terminus2,
            "_execute_commands",
            new_callable=AsyncMock,
            return_value=(False, self.output),
        ):
            for _ in range(4):
                result = await agent._execute_commands(self.commands, None)
                self.assertEqual(result, (False, self.output))

        self.assertEqual(agent._detector.interventions, 0)


if __name__ == "__main__":
    unittest.main()