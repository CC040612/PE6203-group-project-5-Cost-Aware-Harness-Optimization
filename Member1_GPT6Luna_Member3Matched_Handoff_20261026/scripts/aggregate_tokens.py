#!/usr/bin/env python3
"""Aggregate observed Harbor trajectory token metrics for the matched baseline."""
import json
from pathlib import Path

JOBS = Path("/home/member2/experiments/member1/jobs")
OUT = Path(
    "/mnt/d/夏嫣然/6203/group project/member1/handoff/"
    "Member1_GPT6Luna_Member3Matched_Handoff_20261026/reports/token_usage.json"
)
EXACT = [
    "gpt6luna-member3-matched-baseline-formal-20261025T113533Z",
    "gpt6luna-member3-matched-baseline-formal-rerun-20261025T115523Z",
    "gpt6luna-member3-matched-baseline-formal-continue-20261025T122500Z",
    "gpt6luna-member3-matched-baseline-formal-resume-20261025T155552Z",
    "gpt6luna-member3-matched-baseline-formal-resume-20261025T164228Z",
]
PREFIX = "gpt6luna-member3-matched-baseline-resilient-20261025T164947Z-task-"


def as_int(value):
    return int(value) if isinstance(value, (int, float)) else 0


def metrics_for(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    final = data.get("final_metrics") if isinstance(data, dict) else None
    if isinstance(final, dict):
        return {
            "prompt_tokens": as_int(final.get("total_prompt_tokens")),
            "completion_tokens": as_int(final.get("total_completion_tokens")),
            "cached_tokens": as_int(final.get("total_cached_tokens")),
            "source": "trajectory.final_metrics",
        }
    steps = data.get("steps", []) if isinstance(data, dict) else []
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}
    for step in steps if isinstance(steps, list) else []:
        metrics = step.get("metrics", {}) if isinstance(step, dict) else {}
        if not isinstance(metrics, dict):
            continue
        totals["prompt_tokens"] += as_int(metrics.get("prompt_tokens"))
        totals["completion_tokens"] += as_int(metrics.get("completion_tokens"))
        totals["cached_tokens"] += as_int(metrics.get("cached_tokens"))
    totals["source"] = "sum of recorded step metrics; trajectory had no final_metrics"
    return totals


def main():
    dirs = [JOBS / name for name in EXACT]
    dirs.extend(sorted(JOBS.glob(PREFIX + "*")))
    files = []
    for job in dirs:
        if job.is_dir():
            files.extend(sorted(job.rglob("agent/trajectory.json")))
    per_job = {}
    failures = []
    for trajectory in files:
        job_name = trajectory.parents[2].name
        try:
            metric = metrics_for(trajectory)
        except Exception as exc:
            failures.append({"path": str(trajectory), "error": type(exc).__name__})
            continue
        row = per_job.setdefault(job_name, {
            "trajectory_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "fallback_trajectory_count": 0,
        })
        row["trajectory_count"] += 1
        row["prompt_tokens"] += metric["prompt_tokens"]
        row["completion_tokens"] += metric["completion_tokens"]
        row["cached_tokens"] += metric["cached_tokens"]
        if metric["source"] != "trajectory.final_metrics":
            row["fallback_trajectory_count"] += 1
    total = {
        key: sum(row[key] for row in per_job.values())
        for key in ("prompt_tokens", "completion_tokens", "cached_tokens")
    }
    preflight = {"prompt_tokens": 10, "completion_tokens": 5, "requests": 1}
    report = {
        "scope": "All matched-baseline attempts in listed run segments, including failed and cancelled attempts.",
        "trajectory_count": sum(row["trajectory_count"] for row in per_job.values()),
        "trajectory_parse_failures": failures,
        "trajectory_totals": total,
        "diagnostic_generation_preflight": preflight,
        "observed_total_including_preflight": {
            "prompt_tokens": total["prompt_tokens"] + preflight["prompt_tokens"],
            "completion_tokens": total["completion_tokens"] + preflight["completion_tokens"],
            "cached_tokens": total["cached_tokens"],
        },
        "per_job": per_job,
        "limitations": [
            "Provider-side usage for failed requests that never produced a trajectory response is unavailable.",
            "The 10 prompt and 5 completion tokens from the minimal API preflight are included separately.",
            "This is token usage, not a verified monetary charge.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
