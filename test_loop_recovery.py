import unittest

from member3.loop_recovery import RepeatFailureDetector


class DetectorTests(unittest.TestCase):
    def test_triggers_on_third_identical_failure(self):
        detector = RepeatFailureDetector()
        for _ in range(2):
            self.assertIsNone(
                detector.observe(["missing_tool\n"], "missing_tool: command not found")
            )
        event = detector.observe(
            ["missing_tool\n"], "missing_tool: command not found"
        )
        self.assertEqual(event["repeat_count"], 3)

    def test_success_breaks_failure_streak(self):
        detector = RepeatFailureDetector()
        detector.observe(["x\n"], "command not found")
        detector.observe(["x\n"], "command not found")
        detector.observe(["echo ok\n"], "ok")
        self.assertIsNone(detector.observe(["x\n"], "command not found"))

    def test_changed_error_breaks_streak(self):
        detector = RepeatFailureDetector()
        detector.observe(["x\n"], "command not found")
        detector.observe(["x\n"], "command not found")
        self.assertIsNone(detector.observe(["x\n"], "Permission denied"))

    def test_polling_empty_batches_and_timeout_are_ignored(self):
        for commands, timeout in [
            (["sleep 1\n"], False),
            (["\n"], False),
            ([], False),
            (["x\n", "y\n"], False),
            (["x\n"], True),
        ]:
            detector = RepeatFailureDetector()
            for _ in range(5):
                self.assertIsNone(
                    detector.observe(commands, "command not found", timeout)
                )

    def test_intervention_limit(self):
        detector = RepeatFailureDetector(max_interventions=2)
        events = [
            detector.observe(["x\n"], "command not found")
            for _ in range(12)
        ]
        self.assertEqual(sum(event is not None for event in events), 2)


if __name__ == "__main__":
    unittest.main()