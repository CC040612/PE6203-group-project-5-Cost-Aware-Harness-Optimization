import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harbor.agents.terminus_2.terminus_2 import Command, Terminus2
from member3.loop_recovery import LoopRecoveryTerminus2


class FakeSession:
    """模拟终端边界，不执行真实命令。"""

    def __init__(self):
        self.calls = []

    async def send_keys(self, keystrokes, **kwargs):
        self.calls.append((keystrokes, kwargs))

    async def get_incremental_output(self):
        return "missing_tool: command not found"


class ParentExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_parent_execution_reaches_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)

            # 只跳过模型初始化，保留父类真实命令执行方法。
            with patch.object(Terminus2, "__init__", return_value=None):
                agent = LoopRecoveryTerminus2(logs_dir=logs_dir)

            agent._n_episodes = 0
            session = FakeSession()
            commands = [
                Command(keystrokes="missing_tool\n", duration_sec=1)
            ]
            results = []

            for episode in range(1, 4):
                agent._n_episodes = episode
                results.append(
                    await agent._execute_commands(commands, session)
                )

            self.assertEqual(len(session.calls), 3)
            for keystrokes, kwargs in session.calls:
                self.assertEqual(keystrokes, "missing_tool\n")
                self.assertFalse(kwargs["block"])
                self.assertEqual(kwargs["min_timeout_sec"], 1)

            for timeout, output in results[:2]:
                self.assertFalse(timeout)
                self.assertEqual(output, "missing_tool: command not found")

            timeout, output = results[2]
            self.assertFalse(timeout)
            self.assertIn("[Harness recovery notice]", output)
            self.assertTrue(
                output.endswith("missing_tool: command not found")
            )

            events = (
                logs_dir / "loop_recovery_events.jsonl"
            ).read_text(encoding="utf-8").splitlines()

            self.assertEqual(len(events), 1)
            event = json.loads(events[0])
            self.assertEqual(event["repeat_count"], 3)
            self.assertEqual(event["command"], "missing_tool\n")


if __name__ == "__main__":
    unittest.main()
