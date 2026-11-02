"""Supervise a baseline without interpreting traceback text or rerunning tasks."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_EXCEPTION_TYPES = {
    'AuthenticationError', 'PermissionDeniedError', 'RateLimitError',
    'APIConnectionError', 'APITimeoutError', 'BadRequestError',
    'UnprocessableEntityError', 'UnsupportedParamsError',
    'ServiceUnavailableError', 'InternalServerError',
}


def is_infrastructure_fault(info):
    # Deliberately never read exception_message or traceback. A stack frame's
    # "line 401" is not an HTTP response. The official time budget is an outcome.
    kind = str(info.get('exception_type') or '').rsplit('.', 1)[-1]
    if kind == 'AgentTimeoutError':
        return False
    return kind in API_EXCEPTION_TYPES


def now():
    return datetime.now(timezone.utc).isoformat()


def read_results(job):
    records = []
    for path in sorted(job.glob('*/result.json')):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        info = data.get('exception_info') or {}
        records.append({
            'trial': path.parent.name,
            'rewards': (data.get('verifier_result') or {}).get('rewards'),
            'exception_type': info.get('exception_type'),
            'infrastructure_fault': is_infrastructure_fault(info),
            'result_file': str(path),
        })
    return records


def stop(process):
    # Only signal the process group created for this run; never other jobs.
    for sig, seconds in [(signal.SIGINT, 15), (signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A Harbor command is required')
    config = json.loads(args.config.read_text())
    job = Path(config['jobs_dir']) / config['job_name']
    if job.exists():
        raise SystemExit('Job directory already exists; refusing to rerun or overwrite it.')
    state = {
        'status': 'starting', 'started_utc': now(), 'config': str(args.config),
        'job_name': config['job_name'], 'job_directory': str(job),
        'planned_trials': len(config['tasks']) * config['n_attempts'],
        'automatic_reruns': False,
        'stop_rule': 'Known structured API exception types only; never traceback text. AgentTimeoutError never stops the round.',
    }
    state_path = ROOT / 'logs' / f"{config['job_name']}_state.json"

    def save():
        state['updated_utc'] = now()
        records = read_results(job)
        state['completed_trial_results'] = len(records)
        state['trial_summaries'] = records
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(8):
            try:
                temporary.replace(state_path)
                break
            except PermissionError as exc:
                if attempt == 7:
                    print(
                        f"Warning: state snapshot is temporarily locked ({exc}); "
                        "continuing the benchmark and retrying on the next update.",
                        file=sys.stderr, flush=True,
                    )
                    try:
                        temporary.unlink()
                    except OSError:
                        pass
                    break
                time.sleep(0.05 * (attempt + 1))
        return records

    state_path.parent.mkdir(parents=True, exist_ok=True)
    save()
    process = subprocess.Popen(command, start_new_session=True)
    state.update(status='running', harbor_process_pid=process.pid)
    try:
        while process.poll() is None:
            records = save()
            fault = next((r for r in records if r['infrastructure_fault']), None)
            if fault:
                state.update(status='stopping_for_api_fault', infrastructure_fault=fault)
                save()
                print(f"Structured API fault: {fault['exception_type']}; retaining all records and stopping without reruns.", flush=True)
                stop(process)
                state.update(status='stopped_api_fault', exit_code=process.returncode, finished_utc=now())
                save()
                return 3
            time.sleep(2)
        records = read_results(job)
        fault = next((r for r in records if r['infrastructure_fault']), None)
        status = 'finished' if process.returncode == 0 else 'stopped_with_error'
        if fault:
            status = 'finished_with_api_fault'
            state['infrastructure_fault'] = fault
        state.update(status=status, exit_code=process.returncode, finished_utc=now())
        save()
        return 3 if fault else process.returncode
    except BaseException:
        stop(process)
        state.update(status='interrupted', exit_code=process.returncode, finished_utc=now())
        save()
        raise


if __name__ == '__main__':
    sys.exit(main())
