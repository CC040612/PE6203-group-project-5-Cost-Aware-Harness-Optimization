"""Supervise an authorized job; stop on infrastructure/API faults, never rerun."""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "config" / "active-formal-run.json"
FAULT = re.compile(r"authentication|invalid.?api.?key|unauthorized|permissiondeniederror|ratelimit|rate.limit|insufficient.quota|quota.exceeded|usage.limit|subscription_sharing|apiconnection|apitimeout|badrequesterror|unprocessableentity|unsupportedparams|litellm.*error|connecterror|connection refused|401\b|403\b|429\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def save(state):
    state["updated_utc"] = now()
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def results(job):
    records = []
    for path in job.glob("*/result.json"):
        try:
            records.append((path, json.loads(path.read_text())))
        except (OSError, ValueError):
            continue
    return records


def stop(process):
    for sig, wait in ((signal.SIGINT, 15), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=wait)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    config = json.loads(args.config.read_text())
    assert len(config["tasks"]) == 40 and config["n_attempts"] == 1
    assert config["timeout_multiplier"] == config["agent_timeout_multiplier"] == 1.0
    assert "max_turns" not in config["agents"][0]["kwargs"]
    job = Path(config["jobs_dir"]) / config["job_name"]
    state = {"status": "starting", "started_utc": now(), "job_name": config["job_name"],
             "config": str(args.config), "job_directory": str(job), "planned_tasks": 40,
             "attempts_per_task": 1, "concurrency": config["n_concurrent_trials"],
             "agent_timeout_sec": 2400, "max_turns": "original default", "completed_trial_results": 0,
             "authorization": "User explicitly requested starting one formal round", "automatic_reruns": False,
             "stop_policy": "Stop on structured API/auth/connection/quota faults; normal failed tasks remain in the round"}
    save(state)
    process = subprocess.Popen(command, start_new_session=True)
    state.update(status="running", supervisor_pid=os.getpid(), harbor_process_pid=process.pid)
    save(state)
    try:
        while process.poll() is None:
            records = results(job)
            state["completed_trial_results"] = len(records)
            state["trial_summaries"] = []
            fault = None
            for path, data in records:
                info = data.get("exception_info") or {}
                rewards = (data.get("verifier_result") or {}).get("rewards")
                state["trial_summaries"].append({"trial": path.parent.name, "rewards": rewards, "exception_type": info.get("exception_type")})
                if info and FAULT.search(json.dumps(info, ensure_ascii=False)):
                    fault = {"trial": path.parent.name, "exception_type": info.get("exception_type"), "result_file": str(path)}
                    break
            if fault:
                state.update(status="stopping_for_infrastructure_fault", infrastructure_fault=fault)
                save(state)
                print("Pausing formal run after an API/infrastructure fault. Original trial results retained; no automatic rerun.", flush=True)
                stop(process)
                state.update(status="paused_infrastructure_fault", exit_code=process.returncode)
                save(state)
                return 3
            save(state)
            time.sleep(2)
        state.update(status="finished" if process.returncode == 0 else "stopped_with_error", exit_code=process.returncode,
                     completed_trial_results=len(results(job)), finished_utc=now())
        save(state)
        return process.returncode
    except BaseException:
        stop(process)
        state.update(status="interrupted", exit_code=process.returncode)
        save(state)
        raise


if __name__ == "__main__":
    sys.exit(main())
