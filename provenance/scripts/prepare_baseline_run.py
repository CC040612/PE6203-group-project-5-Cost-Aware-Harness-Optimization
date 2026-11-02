"""Prepare validated Harbor job configurations without making model calls."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from harbor.models.job.config import JobConfig
from harbor.environments.docker.docker import DockerEnvironment

PINNED_COMMIT = "3497fd320abcafaf4797424192c891a593fd7964"
PINNED_TASKSET_SHA256 = "07f474182d54a6ba08ce46693e13ddaf7dcd5ff7b07d53713ea2f98d172d6cfd"
TASKSET_ID = "group_approved_40_20261021"
SHARED = Path(__file__).resolve().parents[1]
REPO = Path("/home/member2/TUA-Bench")
MODEL = "openrouter/openai/gpt-6.1-sol"
CONFIG_ID = "gpt61sol_default"
AGENT_KWARGS = {"temperature": None, "reasoning_effort": "medium"}
ADAPTER_IMPORT_PATH = "log_permissions_env:WritableLogsDockerEnvironment"
ADAPTER_SHA256 = "163632ee25e55524e9a666dfa8f295b5413e6aa0e2d075266bce7babf22bd14a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["smoke", "formal"])
    parser.add_argument("--provider", choices=["openrouter", "cockpit-local"], default="openrouter")
    parser.add_argument("--repeats", type=int, choices=[1, 3], default=3)
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    is_cockpit = args.provider == "cockpit-local"
    model = "openai/gpt-6.1-sol" if is_cockpit else MODEL
    agent_kwargs = dict(AGENT_KWARGS)
    config_id = CONFIG_ID
    if is_cockpit:
        agent_kwargs["api_base"] = "http://127.0.0.1:58429/v1"
        agent_kwargs["llm_kwargs"] = {"allowed_openai_params": ["reasoning_effort"]}
        config_id = "gpt61sol_default_cockpit"
    actual_commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_commit != PINNED_COMMIT:
        raise SystemExit("Repository commit differs from the agreed version.")
    adapter_file = SHARED / "adapters" / "log_permissions_env.py"
    if hashlib.sha256(adapter_file.read_bytes()).hexdigest() != ADAPTER_SHA256:
        raise SystemExit("Log permission adapter differs from the shared group file.")
    sys.path.insert(0, str(adapter_file.parent))
    from log_permissions_env import WritableLogsDockerEnvironment
    if not issubclass(WritableLogsDockerEnvironment, DockerEnvironment):
        raise SystemExit("The shared log permission adapter is not a Docker environment.")
    subset_file = SHARED / "config" / "tasks40_approved.txt"
    subset_raw = subset_file.read_bytes()
    subset_sha256 = hashlib.sha256(subset_raw).hexdigest()
    if subset_sha256 != PINNED_TASKSET_SHA256:
        raise SystemExit("Task list differs from the approved group list; verify it before running.")
    names = [line.strip() for line in subset_raw.decode("utf-8-sig").splitlines() if line.strip()]
    if len(names) != 40 or len(set(names)) != 40:
        raise SystemExit("The formal subset must contain exactly 40 unique tasks.")
    if any(not name.startswith("tasks/") or len(Path(name).parts) != 2 or Path(name).name in (".", "..") for name in names):
        raise SystemExit("Each approved task must be a direct tasks/<task-name> path.")
    selected = names[:1] if args.mode == "smoke" else names
    tasks = []
    for name in selected:
        path = REPO / name
        if not (path / "task.toml").is_file():
            raise SystemExit(f"Missing task: {name}")
        tasks.append({"path": str(path)})
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    provider_tag = "-cockpit" if is_cockpit else ""
    job_name = f"gpt61sol{provider_tag}-{args.mode}-{stamp}"
    config = JobConfig.model_validate({
        "job_name": job_name,
        "jobs_dir": "/home/member2/experiments/jobs",
        "n_attempts": 1 if args.mode == "smoke" else args.repeats,
        "n_concurrent_trials": 1 if args.mode == "smoke" else args.concurrency,
        "timeout_multiplier": 1.0,
        "agent_timeout_multiplier": 1.0,
        "retry": {"max_retries": 0},
        "agents": [{"name": "terminus-2", "model_name": model, "kwargs": agent_kwargs}],
        "environment": {"import_path": ADAPTER_IMPORT_PATH, "delete": True, "force_build": False},
        "tasks": tasks,
    })
    output = SHARED / "config" / "generated"
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / f"{job_name}.json"
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    metadata = {
        "job_name": job_name,
        "mode": args.mode,
        "benchmark_commit": actual_commit,
        "model": model,
        "config_id": config_id,
        "provider_profile": args.provider,
        "agent_kwargs": agent_kwargs,
        "decoding_settings": AGENT_KWARGS,
        "shared_budget": {"agent_timeout_sec": 2400, "timeout_multiplier": 1.0, "max_turns": "original Terminus-2 default; no explicit cap", "note": "Use the group-approved repetition/concurrency settings. No additional 10-turn or 300-second pilot restriction."},
        "transport": "WSL local raw TCP bridge via Windows interop to Cockpit Rust gateway; gateway translates Chat Completions to its selected upstream route" if is_cockpit else "OpenRouter",
        "accounting_note": "Gateway estimates and Harbor API-equivalent cost are not evidence of subscription cash billing. Record actual upstream route and request IDs, including fallback and retries." if is_cockpit else "Record actual OpenRouter billed usage alongside Harbor cost estimates.",
        "retry_note": "Job retry is zero. Installed Harbor LiteLLM.call can make up to 3 outer attempts for eligible failures; SDK and gateway recovery are separate layers.",
        "parameter_compatibility_note": "GPT-6.1 Sol does not support temperature=0.7; use null rather than sending a sampling value. Reasoning effort is explicitly medium. Original Terminus-2 JSON plain parser and Chat Completions path are retained; this parser does not use native API tool calls.",
        "task_count": len(selected),
        "attempts_per_task": config.n_attempts,
        "total_trials": len(selected) * config.n_attempts,
        "task_names": selected,
        "taskset_id": TASKSET_ID,
        "taskset_file": str(subset_file),
        "fixed_subset_sha256": subset_sha256,
        "selected_tasks_are_in_approved_subset": all(name in names for name in selected),
        "log_permission_adapter": {
            "import_path": ADAPTER_IMPORT_PATH,
            "source_file": str(adapter_file),
            "sha256": ADAPTER_SHA256,
            "source": "Group-provided log_permissions_env.py, preserved byte-for-byte",
            "scope": "Create and chmod only /logs/agent, /logs/verifier and /logs/artifacts within Linux task containers; official task and verifier files are unchanged",
            "runtime_validation": "See config/log-permissions-validation.json; config preparation alone does not start a container",
        },
        "config": str(config_path),
        "job_directory": str(config.jobs_dir / job_name),
        "model_calls_made_by_preparation": 0,
    }
    (output / f"{job_name}.meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(config_path)


if __name__ == "__main__":
    main()
