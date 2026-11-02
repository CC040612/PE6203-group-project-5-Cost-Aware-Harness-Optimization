import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harbor.agents.terminus_2.terminus_2 import Terminus2
from member3.loop_recovery import LoopRecoveryTerminus2
from member3.idle_recovery import IdleDetector, IdleRecoveryTerminus2


class IdleDetectorTests(unittest.TestCase):
    def test_third_same_idle_response_triggers(self):
        d = IdleDetector()
        self.assertIsNone(d.observe("unchanged", True))
        self.assertIsNone(d.observe("unchanged", True))
        self.assertEqual(d.observe("unchanged", True)["repeat_count"], 3)

    def test_action_or_changed_output_breaks_streak(self):
        d = IdleDetector()
        d.observe("a", True)
        d.observe("a", True)
        self.assertIsNone(d.observe("b", True))
        d.observe("b", False)
        self.assertIsNone(d.observe("b", True))
        self.assertEqual(d.count, 1)

    def test_intervention_limit(self):
        d = IdleDetector(max_interventions=2)
        events = [d.observe("", True) for _ in range(12)]
        self.assertEqual(sum(e is not None for e in events), 2)


class IdleIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_notice_and_event_preserve_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Terminus2, "__init__", return_value=None):
                agent = IdleRecoveryTerminus2(logs_dir=Path(tmp))
            with patch.object(
                LoopRecoveryTerminus2, "_execute_commands",
                new_callable=AsyncMock, return_value=(False, "unchanged"),
            ):
                for _ in range(2):
                    self.assertEqual(
                        await agent._execute_commands([], None),
                        (False, "unchanged"),
                    )
                timeout, output = await agent._execute_commands([], None)

            self.assertFalse(timeout)
            self.assertIn("[Harness idle recovery notice]", output)
            self.assertTrue(output.endswith("unchanged"))
            self.assertEqual(
                len((Path(tmp) / "idle_recovery_events.jsonl")
                    .read_text().splitlines()), 1
            )

    async def test_completion_parsing_timeout_and_disabled_are_unchanged(self):
        for case in ("completion", "parsing", "timeout", "disabled", "action"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                with patch.object(Terminus2, "__init__", return_value=None):
                    agent = IdleRecoveryTerminus2(
                        logs_dir=Path(tmp),
                        enable_idle_recovery=(case != "disabled"),
                    )
                agent._completion_requested = case == "completion"
                agent._idle_parse_error = case == "parsing"
                expected = (case == "timeout", "unchanged")
                commands = [object()] if case == "action" else []
                with patch.object(
                    LoopRecoveryTerminus2, "_execute_commands",
                    new_callable=AsyncMock, return_value=expected,
                ):
                    for _ in range(4):
                        self.assertEqual(
                            await agent._execute_commands(commands, None),
                            expected,
                        )
                self.assertFalse(
                    (Path(tmp) / "idle_recovery_events.jsonl").exists()
                )


if __name__ == "__main__":
    unittest.main()
