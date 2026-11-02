#!/usr/bin/env python3
"""Run tasks one at a time, recording per-task errors and continuing."""
import copy
import json
import os
import signal
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path("/home/member2/TUA-Bench")
RUN_SCRIPT = ROOT / "scripts" / "run_baseline.sh"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_state(path: Path, state: dict):
    state["updated_utc"] = utc_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                print("Warning: status file remained locked; continuing task loop.", file=sys.stderr, flush=True)
                try:
                    tmp.unlink()
                except OSError:
                    pass
                return
            time.sleep(0.05 * (attempt + 1))


def read_child_result(child_state_path: Path, child_config: dict):
    try:
        data = json.loads(child_state_path.read_text(encoding="utf-8"))
        summaries = data.get("trial_summaries") or []
        if summaries:
            item = summaries[-1]
            return {
                "trial": item.get("trial"),
                "rewards": item.get("rewards"),
                "exception_type": item.get("exception_type"),
                "infrastructure_fault": item.get("infrastructure_fault", False),
                "result_file": item.get("result_file"),
                "child_status": data.get("status"),
            }
    except (OSError, ValueError):
        pass
    job = Path(child_config["jobs_dir"]) / child_config["job_name"]
    try:
        for result_path in sorted(job.glob("*/result.json")):
            data = json.loads(result_path.read_text(encoding="utf-8"))
            info = data.get("exception_info") or {}
            return {
                "trial": result_path.parent.name,
                "rewards": (data.get("verifier_result") or {}).get("rewards"),
                "exception_type": info.get("exception_type"),
                "infrastructure_fault": False,
                "result_file": str(result_path),
                "child_status": "result_file_fallback",
            }
    except (OSError, ValueError):
        pass
    return None


def stop_process_group(process: subprocess.Popen):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=20)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def task_timeout_sec(task: dict) -> int:
    task_dir = Path(task["path"])
    try:
        task_config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        return int(task_config["agent"]["timeout_sec"])
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError):
        return 2400


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: resilient_run.py CONFIG.json")
    source = Path(sys.argv[1]).resolve()
    base = json.loads(source.read_text(encoding="utf-8"))
    tasks = list(base["tasks"])
    base_name = base["job_name"]
    state_path = ROOT / "logs" / f"{base_name}_state.json"
    config_dir = ROOT / "config" / "generated"
    config_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "status": "running",
        "started_utc": utc_now(),
        "config": str(source),
        "job_name": base_name,
        "job_directory": base["jobs_dir"],
        "planned_trials": len(tasks) * int(base.get("n_attempts", 1)),
        "completed_trial_results": 0,
        "automatic_reruns": False,
        "execution_policy": "Per-task isolation: record errors/timeouts and continue to the next task; no automatic retry.",
        "trial_summaries": [],
        "current_task": None,
        "task_timeout_sec": 2400,
    }
    write_state(state_path, state)
    controller_log_path = ROOT / "logs" / f"{base_name}_controller.log"
    controller_log = controller_log_path.open("a", encoding="utf-8")
    active_process = None
    try:
        for index, task in enumerate(tasks, start=1):
            task_name = Path(task["path"]).name
            child_name = f"{base_name}-task-{task_name}"
            child_config = copy.deepcopy(base)
            child_config["job_name"] = child_name
            child_config["tasks"] = [task]
            child_config_path = config_dir / f"{child_name}.json"
            child_config_path.write_text(json.dumps(child_config, ensure_ascii=False, indent=2), encoding="utf-8")
            child_state_path = ROOT / "logs" / f"{child_name}_state.json"
            timeout = task_timeout_sec(task)
            state["current_task"] = {"index": index, "name": task_name, "started_utc": utc_now()}
            state["task_timeout_sec"] = timeout
            state["status"] = "running"
            write_state(state_path, state)
            env = os.environ.copy()
            env["RUN_CONFIG"] = str(child_config_path)
            started = time.monotonic()
            active_process = subprocess.Popen(
                ["bash", str(RUN_SCRIPT), "formal", "run"],
                cwd=REPO,
                env=env,
                start_new_session=True,
                stdout=controller_log,
                stderr=subprocess.STDOUT,
            )
            timed_out = False
            while active_process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    timed_out = True
                    state["status"] = "skipping_timed_out_task"
                    state["current_task"]["timed_out_after_sec"] = timeout
                    write_state(state_path, state)
                    print(f"Task {task_name} exceeded {timeout}s; interrupting this task and continuing.", file=controller_log, flush=True)
                    stop_process_group(active_process)
                    break
                time.sleep(2)
            return_code = active_process.wait()
            summary = read_child_result(child_state_path, child_config)
            if summary is None:
                summary = {
                    "trial": task_name,
                    "rewards": None,
                    "exception_type": "TaskTimeoutError" if timed_out else f"RunExit{abs(return_code)}",
                    "infrastructure_fault": False,
                    "result_file": None,
                    "child_status": "skipped",
                }
            if timed_out and summary.get("exception_type") is None:
                summary["exception_type"] = "TaskTimeoutError"
            summary["task"] = task_name
            summary["task_index"] = index
            summary["timed_out"] = timed_out
            state["trial_summaries"].append(summary)
            state["completed_trial_results"] = len(state["trial_summaries"])
            state["current_task"] = None
            state["status"] = "running"
            write_state(state_path, state)
            print(
                f"[{index}/{len(tasks)}] {task_name}: "
                f"{summary.get('exception_type') or summary.get('rewards')}",
                file=controller_log,
                flush=True,
            )
            active_process = None
        failed = [x for x in state["trial_summaries"] if x.get("exception_type")]
        state["status"] = "finished_with_task_errors" if failed else "finished"
        state["finished_utc"] = utc_now()
        state["current_task"] = None
        write_state(state_path, state)
        return 0
    except KeyboardInterrupt:
        if active_process is not None:
            stop_process_group(active_process)
        state["status"] = "interrupted"
        state["finished_utc"] = utc_now()
        write_state(state_path, state)
        return 130
    except BaseException as exc:
        if active_process is not None:
            stop_process_group(active_process)
        state["status"] = "controller_error"
        state["controller_error_type"] = type(exc).__name__
        state["finished_utc"] = utc_now()
        write_state(state_path, state)
        print(f"Controller stopped: {type(exc).__name__}: {exc}", file=controller_log, flush=True)
        return 1
    finally:
        controller_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
