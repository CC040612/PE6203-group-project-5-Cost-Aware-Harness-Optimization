"""Add recovery for repeated no-action responses without changing the old agent."""
import json
from datetime import datetime, timezone
from pathlib import Path

from member3.loop_recovery import LoopRecoveryTerminus2, RepeatFailureDetector


class IdleDetector:
    def __init__(self, threshold=3, max_interventions=2):
        if threshold < 2 or max_interventions < 0:
            raise ValueError("Invalid idle detector limits")
        self.threshold = threshold
        self.max_interventions = max_interventions
        self.interventions = 0
        self.reset()

    def reset(self):
        self.last_output = None
        self.count = 0

    def observe(self, output, eligible):
        if not eligible:
            self.reset()
            return None

        cleaned = RepeatFailureDetector.ANSI.sub("", output)
        cleaned = cleaned.replace("\r\n", "\n").strip()
        self.count = self.count + 1 if cleaned == self.last_output else 1
        self.last_output = cleaned

        if (
            self.count < self.threshold
            or self.interventions >= self.max_interventions
        ):
            return None

        event = {
            "kind": "no_action",
            "repeat_count": self.count,
            "intervention": self.interventions + 1,
            "output": cleaned,
        }
        self.interventions += 1
        self.reset()
        return event


class IdleRecoveryTerminus2(LoopRecoveryTerminus2):
    def __init__(
        self,
        logs_dir,
        *args,
        enable_idle_recovery=True,
        idle_threshold=3,
        max_idle_interventions=2,
        **kwargs,
    ):
        if isinstance(enable_idle_recovery, str):
            value = enable_idle_recovery.lower()
            if value not in ("true", "false"):
                raise ValueError("enable_idle_recovery must be true or false")
            enable_idle_recovery = value == "true"

        self._idle_enabled = bool(enable_idle_recovery)
        self._idle_detector = IdleDetector(
            int(idle_threshold), int(max_idle_interventions)
        )
        self._idle_parse_error = False
        self._idle_event_path = Path(logs_dir) / "idle_recovery_events.jsonl"
        super().__init__(logs_dir, *args, **kwargs)

    async def _handle_llm_interaction(self, *args, **kwargs):
        result = await super()._handle_llm_interaction(*args, **kwargs)
        self._idle_parse_error = bool(result[2] and "ERROR:" in result[2])
        if self._idle_parse_error:
            self._idle_detector.reset()
        return result

    async def _execute_commands(self, commands, session):
        timeout, output = await super()._execute_commands(commands, session)

        if not self._idle_enabled:
            return timeout, output

        event = self._idle_detector.observe(
            output,
            eligible=(
                not commands
                and not timeout
                and not self._completion_requested
                and not self._idle_parse_error
            ),
        )
        if event is None:
            return timeout, output

        notice = (
            "[Harness idle recovery notice]\n"
            "Several consecutive responses issued no commands while the "
            "terminal feedback stayed unchanged. Repeating an inability "
            "statement does not advance the task. Choose a concrete, minimal "
            "diagnostic or recovery action appropriate to the current state. "
            "If a foreground process is blocking the shell, consider whether "
            "interrupting it is appropriate; otherwise try another approach. "
            "Do not claim completion without evidence. "
            "Follow the original task and response format.\n"
            "[Terminal output]\n"
        )
        event.update(
            timestamp=datetime.now(timezone.utc).isoformat(),
            episode=getattr(self, "_n_episodes", None),
            notice=notice,
        )
        self._idle_event_path.parent.mkdir(parents=True, exist_ok=True)
        with self._idle_event_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        return timeout, notice + output
