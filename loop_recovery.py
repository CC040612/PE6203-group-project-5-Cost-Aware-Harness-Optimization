import json
import re
from datetime import datetime, timezone
from pathlib import Path

from harbor.agents.terminus_2.terminus_2 import Terminus2


class RepeatFailureDetector:
    """Detect consecutive identical commands with identical error output."""

    ERROR = re.compile(
        r"command not found|no such file or directory|permission denied|"
        r"ModuleNotFoundError:|ImportError:|SyntaxError:|"
        r"Traceback \(most recent call last\):",
        re.IGNORECASE,
    )
    ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    WAIT = re.compile(
        r"^(sleep|wait|watch|tail|top|htop|ps)(?:\s|$)"
        r"|^docker\s+logs(?:\s|$)"
    )

    def __init__(self, threshold=3, max_interventions=2):
        if threshold < 2 or max_interventions < 0:
            raise ValueError("Invalid detector limits")
        self.threshold = threshold
        self.max_interventions = max_interventions
        self.interventions = 0
        self.reset_streak()

    def reset_streak(self):
        self.last_key = None
        self.count = 0

    def observe(self, keystrokes, output, timeout=False):
        if timeout or len(keystrokes) != 1:
            self.reset_streak()
            return None

        raw_command = keystrokes[0]
        command = raw_command.strip()
        cleaned = self.ANSI.sub("", output).replace("\r\n", "\n").strip()

        if (
            not command
            or "\n" in command
            or any(ord(char) < 32 for char in command)
            or self.WAIT.search(command)
            or not cleaned
            or not self.ERROR.search(cleaned)
        ):
            self.reset_streak()
            return None

        key = (raw_command, cleaned)
        self.count = self.count + 1 if key == self.last_key else 1
        self.last_key = key

        if (
            self.count < self.threshold
            or self.interventions >= self.max_interventions
        ):
            return None

        self.interventions += 1
        event = {
            "repeat_count": self.count,
            "intervention": self.interventions,
            "command": raw_command,
            "output": cleaned,
        }
        self.reset_streak()
        return event


class LoopRecoveryTerminus2(Terminus2):
    def __init__(
        self,
        logs_dir,
        *args,
        enable_loop_recovery=True,
        repeat_threshold=3,
        max_interventions=2,
        **kwargs,
    ):
        if isinstance(enable_loop_recovery, str):
            value = enable_loop_recovery.lower()
            if value not in ("true", "false"):
                raise ValueError("enable_loop_recovery must be true or false")
            enable_loop_recovery = value == "true"

        self._recovery_enabled = bool(enable_loop_recovery)
        self._detector = RepeatFailureDetector(
            threshold=int(repeat_threshold),
            max_interventions=int(max_interventions),
        )
        self._completion_requested = False
        self._recovery_event_path = Path(logs_dir) / "loop_recovery_events.jsonl"
        super().__init__(logs_dir, *args, **kwargs)

    async def _handle_llm_interaction(self, *args, **kwargs):
        result = await super()._handle_llm_interaction(*args, **kwargs)
        self._completion_requested = result[1]

        # Parsing errors interrupt the consecutive execution sequence.
        if result[2] and "ERROR:" in result[2]:
            self._detector.reset_streak()

        return result

    async def _execute_commands(self, commands, session):
        timeout, output = await super()._execute_commands(commands, session)

        if not self._recovery_enabled:
            return timeout, output

        if self._completion_requested:
            self._detector.reset_streak()
            return timeout, output

        event = self._detector.observe(
            [command.keystrokes for command in commands],
            output,
            timeout=timeout,
        )
        if event is None:
            return timeout, output

        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        event["episode"] = getattr(self, "_n_episodes", None)

        feedback = (
            "[Harness recovery notice]\n"
            f"The same command and error output repeated "
            f"{event['repeat_count']} consecutive times. "
            "Check the cause before repeating the action. "
            "Choose a diagnostic step or a different approach. "
            "If repetition is intentional, explain why and continue. "
            "Follow the original task and response format.\n"
            "[Terminal output]\n"
        )
        event["notice"] = feedback

        self._recovery_event_path.parent.mkdir(parents=True, exist_ok=True)
        with self._recovery_event_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

        return timeout, feedback + output