"""Preserve this incident and prepare only cancelled trials for job resumption.

No generation requests. Scored results, including timeout/reward zero, stay intact.
"""
import asyncio
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import JobConfig
from guard_formal_run import is_infrastructure_fault

ROOT = Path(__file__).resolve().parents[1]
NAME = "gpt61sol-cockpit-formal-20261021-231816-860550"
JOB = Path("/home/member2/experiments/jobs") / NAME
INCIDENT = Path("/home/member2/experiments/incidents/20261022-0058")
SHARED_INCIDENT = ROOT / "results" / "incident-20261022-0058"
EXPECTED_CANCELLED = {
    "099-professor-contact-info__SGkDxXB",
    "100-name-mountain-photos__StHvEY6",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert JOB.resolve().parent == Path("/home/member2/experiments/jobs").resolve()
    assert not INCIDENT.exists(), "Incident already prepared; inspect instead of repeating"
    source_config = ROOT / "config" / "generated" / (NAME + ".json")
    config = JobConfig.model_validate_json(source_config.read_text())
    assert config == JobConfig.model_validate_json((JOB / "config.json").read_text())
    assert len(config.tasks) == 40 and config.n_attempts == 1
    records = [(p, json.loads(p.read_text())) for p in JOB.glob("*/result.json")]
    cancelled = [(p, d) for p, d in records
                 if (d.get("exception_info") or {}).get("exception_type") == "CancelledError"]
    completed = [(p, d) for p, d in records if p.parent.name not in EXPECTED_CANCELLED]
    assert {p.parent.name for p, _ in cancelled} == EXPECTED_CANCELLED
    assert len(completed) == 23 and all(d.get("verifier_result") for _, d in completed)
    assert all(not is_infrastructure_fault(d.get("exception_info") or {}) for _, d in completed)
    original_hashes = {p.parent.name: digest(p) for p, _ in completed}
    INCIDENT.mkdir(parents=True)
    SHARED_INCIDENT.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "result.json", "lock.json", "job.log"):
        shutil.copy2(JOB / name, INCIDENT / name)
    mapping = []
    for p, d in cancelled:
        destination = INCIDENT / p.parent.name
        # Same filesystem rename preserves every original byte; no deletion.
        p.parent.rename(destination)
        mapping.append({"old_trial": p.parent.name, "original_archive": str(destination),
                        "old_result": d, "replacement_reason": "supervisor false positive interrupted this trial"})
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "job_name": NAME,
        "cause": "Supervisor regex scanned traceback: Python line 401 and litellm text falsely classified AgentTimeoutError as an API fault",
        "model_quota_exhaustion_proven": False,
        "scored_results_preserved": 23, "interrupted_trials_to_restart": 2,
        "never_started_tasks": 15, "remaining_tasks": 17,
        "existing_result_sha256": original_hashes, "archived_interrupted_trials": mapping,
        "source_config_sha256": digest(source_config),
        "cost_accounting": "Include archived interrupted-trial usage plus resumed usage; do not treat API-equivalent USD estimates as cash charges",
        "normal_failures_rerun": False, "extra_pilots": 0,
    }
    report_path = SHARED_INCIDENT / "recovery.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # Construct Harbor's own pending list without running any trial or calling an LLM.
    job = await Job.create(config)
    try:
        pending = [str(c.task.path) for c in job._remaining_trial_configs]
        scored_names = {p.parent.name.split("__", 1)[0] for p, _ in completed}
        expected_pending = [str(t.path) for t in config.tasks if t.path.name not in scored_names]
        assert pending == expected_pending and len(pending) == 17
        assert len(job._existing_trial_results) == 23
        assert all(digest(JOB / name / "result.json") == value for name, value in original_hashes.items())
        report.update(pending_task_paths=pending, harbor_pending_plan_verified=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({"preserved": 23, "archived_cancelled": 2, "pending": 17,
                          "harbor_pending_plan_verified": True, "generation_requests": 0}))
    finally:
        job._close_logger_handlers()


if __name__ == "__main__":
    asyncio.run(main())
