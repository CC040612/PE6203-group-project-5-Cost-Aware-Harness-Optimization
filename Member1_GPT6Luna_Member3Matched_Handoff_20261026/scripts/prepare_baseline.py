"""Prepare Member 1 configs using Member 2's completed round. No model calls."""
import argparse
import copy
import hashlib
import importlib.metadata
import inspect
import json
import platform
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from harbor.models.job.config import JobConfig
from harbor.agents.terminus_2.terminus_2 import Terminus2

ROOT = Path(__file__).resolve().parents[1]
REPO = Path('/home/member2/TUA-Bench')
COMMIT = '3497fd320abcafaf4797424192c891a593fd7964'
TASK_SHA = '07f474182d54a6ba08ce46693e13ddaf7dcd5ff7b07d53713ea2f98d172d6cfd'
ADAPTER_SHA = '163632ee25e55524e9a666dfa8f295b5413e6aa0e2d075266bce7babf22bd14a'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['smoke', 'formal'])
    args = parser.parse_args()
    taskfile = ROOT / 'config/tasks40_approved.txt'
    adapter = ROOT / 'adapters/log_permissions_env.py'
    if sha(taskfile) != TASK_SHA or sha(adapter) != ADAPTER_SHA:
        raise SystemExit('The approved task list or log adapter has changed.')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != COMMIT:
        raise SystemExit('Benchmark commit differs from the shared version.')
    names = taskfile.read_text(encoding='utf-8-sig').splitlines()
    if len(names) != 40 or len(set(names)) != 40:
        raise SystemExit('Expected exactly 40 unique tasks.')
    for name in names:
        config = tomllib.loads((REPO / name / 'task.toml').read_text())
        if config['agent']['timeout_sec'] != 2400:
            raise SystemExit(f'Unexpected task timeout: {name}')
    reference_path = ROOT / 'config/member2_reference.json'
    reference = json.loads(reference_path.read_text())
    if [str(t['path']) for t in reference['tasks']] != [str(REPO / n) for n in names]:
        raise SystemExit('Reference tasks do not match the approved ordered list.')
    if reference['agents'][0]['model_name'] != 'openai/gpt-6.1-sol':
        raise SystemExit('Unexpected reference model.')
    config = copy.deepcopy(reference)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    config['job_name'] = f'gpt6luna-original-{args.mode}-{stamp}'
    config['jobs_dir'] = '/home/member2/experiments/member1/jobs'
    config['agents'][0]['model_name'] = 'openai/gpt-6-luna'
    if args.mode == 'smoke':
        config['tasks'] = config['tasks'][:1]
        config['n_concurrent_trials'] = 1
    if config['n_attempts'] != 1 or config['retry']['max_retries'] != 0:
        raise SystemExit('Expected one attempt and zero job retries.')
    kwargs = config['agents'][0]['kwargs']
    if kwargs != {
        'temperature': None, 'reasoning_effort': 'medium',
        'api_base': 'http://127.0.0.1:58429/v1',
        'llm_kwargs': {'allowed_openai_params': ['reasoning_effort']},
    }:
        raise SystemExit('Reference decoding/transport settings changed.')
    validated = JobConfig.model_validate(config)
    normalized = validated.model_dump(mode='json')
    # Formal configurations must differ only in model and output identity.
    comparison = copy.deepcopy(normalized)
    for key in ['job_name', 'jobs_dir']:
        comparison[key] = reference[key]
    comparison['agents'][0]['model_name'] = reference['agents'][0]['model_name']
    # Retry exception exclusions are sets in Harbor, so JSON list order is immaterial.
    if args.mode == 'formal' and JobConfig.model_validate(comparison) != JobConfig.model_validate(reference):
        differing = [key for key in set(reference) | set(comparison) if reference.get(key) != comparison.get(key)]
        raise SystemExit(f'Unexpected difference from the completed Member 2 round: {differing}')
    out = ROOT / 'config/generated'
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{config['job_name']}.json"
    path.write_text(validated.model_dump_json(indent=2), encoding='utf-8')
    installed_source = Path(inspect.getfile(Terminus2))
    metadata = {
        'prepared_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'prepared_not_executed', 'model_calls': 0,
        'config_id': 'gpt6luna_original_cockpit', 'mode': args.mode,
        'model_requested': 'gpt-6-luna', 'litellm_model': 'openai/gpt-6-luna',
        'benchmark_commit': commit, 'taskset_sha256': TASK_SHA, 'adapter_sha256': ADAPTER_SHA,
        'reference_file': str(reference_path), 'reference_sha256': sha(reference_path),
        'reference_differences': ['job_name', 'jobs_dir', 'agents[0].model_name'] if args.mode == 'formal' else ['job_name', 'jobs_dir', 'agents[0].model_name', 'tasks (first only)', 'n_concurrent_trials (1)'],
        'task_count': len(config['tasks']), 'attempts_per_task': 1,
        'total_trials': len(config['tasks']), 'concurrency': config['n_concurrent_trials'],
        'agent_timeout_sec': 2400, 'max_turns': 'original default, not overridden',
        'loop_recovery_added': False, 'original_summarization_retained': True,
        'job_retries': 0, 'internal_llm_retries': 'original defaults retained',
        'agent_kwargs': kwargs, 'config': str(path),
        'job_directory': str(Path(config['jobs_dir']) / config['job_name']),
        'python': platform.python_version(),
        'packages': {p: importlib.metadata.version(p) for p in ['harbor', 'litellm', 'openai']},
        'uv_lock_sha256': sha(REPO / 'uv.lock'),
        'installed_terminus_source': str(installed_source),
        'installed_terminus_sha256': sha(installed_source),
        'live_generation_verified': False,
        'accounting_note': 'Harbor/gateway cost estimates are not observed subscription cash charges. Keep unknown amounts null; record returned model and upstream route when available.',
    }
    path.with_suffix('.meta.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / f'config/latest-{args.mode}.txt').write_text(str(path) + '\n', encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
