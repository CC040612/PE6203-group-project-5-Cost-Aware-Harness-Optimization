"""Summarize saved benchmark records. No network requests or model calls."""
import csv
import hashlib
import inspect
import json
import math
import statistics
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/01a1575c-2b59-7890-b137-02d160ed18ec"
NAME = "gpt61sol-cockpit-formal-20261021-231816-860550"
JOB = Path("/home/member2/experiments/jobs") / NAME
INCIDENT = Path("/home/member2/experiments/incidents/20261022-0058")
CONFIG_ID = "gpt61sol_default_cockpit"


def load(p):
    return json.loads(p.read_text())


def elapsed(a, b):
    if not a or not b:
        return None
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    approved = [Path(s).name for s in (ROOT / "config/tasks40_approved.txt").read_text().splitlines() if s.strip()]
    job = load(JOB / "result.json")
    assert job['finished_at'] and job['stats']['n_completed_trials'] == 40
    records = {p.parent.name.split('__')[0]: (p, load(p)) for p in JOB.glob('*/result.json')}
    assert set(records) == set(approved) and len(records) == 40
    recovery = load(ROOT / "results/incident-20261022-0058/recovery.json")
    for name, expected in recovery['existing_result_sha256'].items():
        assert hashlib.sha256((JOB / name / 'result.json').read_bytes()).hexdigest() == expected
    replacements = {r['replacement_trial']: r['old_trial'] for r in recovery['archived_interrupted_trials']}
    rows, calls = [], []
    seen = set()
    for task in approved:
        p, d = records[task]
        a = d.get('agent_result') or {}
        meta = a.get('metadata') or {}
        t = load(p.parent / 'agent/trajectory.json')
        trial_calls = []
        for f in sorted((p.parent / 'agent').rglob('debug.json')):
            debug = load(f)
            response = debug.get('original_response')
            if isinstance(response, str):
                response = json.loads(response)
            if not response:
                continue
            rid = response.get('id')
            assert rid and rid not in seen, f'Duplicate response ID: {f}'
            seen.add(rid)
            usage = response.get('usage') or {}
            details = usage.get('completion_tokens_details') or {}
            prompt_details = usage.get('prompt_tokens_details') or {}
            row = dict(config_id=CONFIG_ID, stage='formal', job_id=d['config']['job_id'],
                       trial_id=d['id'], trial_name=d['trial_name'], task_id=task,
                       response_id=rid, call_type='inference', included_in_trial_total=True,
                       model_returned=response.get('model'), upstream_provider=response.get('provider'),
                       actual_route=None, created_utc=datetime.fromtimestamp(response['created'], timezone.utc).isoformat(),
                       prompt_tokens=usage.get('prompt_tokens'), cached_tokens=prompt_details.get('cached_tokens'),
                       completion_tokens=usage.get('completion_tokens'), reasoning_tokens=details.get('reasoning_tokens'),
                       provider_usage_usd=usage.get('cost'), finish_reason=(response.get('choices') or [{}])[0].get('finish_reason'),
                       source_file=f.relative_to(JOB).as_posix())
            trial_calls.append(row)
        assert meta.get('summarization_count') == 0
        for source, dest in [('prompt_tokens', 'n_input_tokens'), ('cached_tokens', 'n_cache_tokens'), ('completion_tokens', 'n_output_tokens')]:
            assert sum(c[source] for c in trial_calls) == a[dest], (task, source)
        calls.extend(trial_calls)
        e = d.get('exception_info') or {}
        score = d['verifier_result']['rewards']['reward']
        assert isinstance(score, (int, float)) and 0 <= score <= 1
        execution = d.get('agent_execution') or {}
        last = next((s for s in reversed(t['steps']) if s.get('source') == 'agent'), {})
        message = last.get('message', '')
        try:
            message = json.loads(message) if isinstance(message, str) else message
        except (ValueError, TypeError):
            message = {}
        complete = message.get('task_complete') if isinstance(message, dict) else None
        stop = 'agent_timeout_2400_sec' if e.get('exception_type') == 'AgentTimeoutError' else ('self_reported_complete' if complete is True else 'agent_returned_for_verification')
        row = dict(config_id=CONFIG_ID, stage='formal', job_id=d['config']['job_id'], trial_id=d['id'],
                   trial_name=d['trial_name'], task_id=task, task_checksum=d['task_checksum'], replicate_index=1,
                   selected_for_evaluation=True, official_reward=score,
                   score_category='满分' if score == 1 else ('零分' if score == 0 else '部分得分'),
                   run_status='agent_timeout' if e else 'scored', exception_type=e.get('exception_type'),
                   stop_reason=stop, agent_started_utc=execution.get('started_at'), agent_finished_utc=execution.get('finished_at'),
                   agent_elapsed_sec=elapsed(execution.get('started_at'), execution.get('finished_at')),
                   trial_started_utc=d['started_at'], trial_finished_utc=d['finished_at'], total_elapsed_sec=elapsed(d['started_at'],d['finished_at']),
                   agent_turns=meta.get('n_episodes'), command_count=sum(len(s.get('tool_calls') or []) for s in t['steps']),
                   observed_response_count=len(trial_calls), prompt_tokens=a['n_input_tokens'], cached_tokens=a['n_cache_tokens'],
                   completion_tokens=a['n_output_tokens'], reasoning_tokens_reported=sum(c['reasoning_tokens'] for c in trial_calls) if all(c['reasoning_tokens'] is not None for c in trial_calls) else None,
                   harbor_total_usd=a['cost_usd'], provider_usage_usd=None, inference_usd=a['cost_usd'], included_overhead_usd=0,
                   additional_unincluded_usd=0, billing_status='API-equivalent estimate; subscription cash charge unavailable',
                   summary_call_count=meta.get('summarization_count'), replacement_for=replacements.get(d['trial_name']),
                   retry_policy='job max_retries=0; internal API retries retained, hidden gateway retries not independently counted',
                   error_evidence=e.get('exception_message'), model_id='openai/gpt-6.1-sol', api_provider='Cockpit local gateway / Plus authorization',
                   agent_timeout_sec=2400, max_turns='original default; no explicit override', cost_budget_usd=None,
                   improvement_A=False, improvement_B=False, source_file=p.relative_to(JOB).as_posix())
        rows.append(row)
    excluded = []
    for p in sorted(INCIDENT.glob('*/result.json')):
        d=load(p)
        assert d.get('agent_execution') is None and not list(p.parent.rglob('debug.json'))
        replacement = next(r['replacement_trial'] for r in recovery['archived_interrupted_trials'] if r['old_trial']==p.parent.name)
        excluded.append(dict(config_id=CONFIG_ID,stage='formal',job_id=d['config']['job_id'],trial_id=d['id'],trial_name=p.parent.name,
                             task_id=p.parent.name.split('__')[0],task_checksum=d['task_checksum'],replicate_index=1,selected_for_evaluation=False,
                             official_reward=None,run_status='cancelled_during_environment_setup',exception_type='CancelledError',
                             agent_started_utc=None,agent_finished_utc=None,agent_elapsed_sec=None,prompt_tokens=None,cached_tokens=None,completion_tokens=None,
                             harbor_total_usd=None,observed_generation_calls=0,replacement_trial_id=records[p.parent.name.split('__')[0]][1]['id'],
                             replacement_trial_name=replacement,total_elapsed_sec=elapsed(d['started_at'],d['finished_at']),
                             stop_reason='supervisor traceback false positive sent SIGINT',
                             cost_note='No agent execution or generation log; missing API cost remains blank, not zero',
                             source_file=f'incident-20261022-0058/{p.parent.name}/result.json'))
    sums = {k:sum(r[k] for r in rows) for k in ['prompt_tokens','cached_tokens','completion_tokens','harbor_total_usd','agent_elapsed_sec','total_elapsed_sec','agent_turns','command_count']}
    for source,dest in [('prompt_tokens','n_input_tokens'),('cached_tokens','n_cache_tokens'),('completion_tokens','n_output_tokens'),('harbor_total_usd','cost_usd')]:
        assert math.isclose(sums[source],job['stats'][dest],abs_tol=1e-8)
    mean = statistics.mean(r['official_reward'] for r in rows)
    assert math.isclose(mean,job['stats']['evals']['terminus-2__gpt-6.1-sol__adhoc']['metrics'][0]['mean'],abs_tol=1e-12)
    top = sorted(rows,key=lambda r:r['harbor_total_usd'],reverse=True)
    versions={'tua_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd='/home/member2/TUA-Bench',text=True).strip()}
    import importlib.metadata, sys
    for name in ['harbor','litellm','openai']:
        versions[name]=importlib.metadata.version(name)
    versions['python']=sys.version.split()[0]
    from harbor.agents.terminus_2.terminus_2 import Terminus2
    versions['terminus_default_max_turns']=inspect.signature(Terminus2.__init__).parameters['max_turns'].default
    result=dict(job_name=NAME,job_id=job['id'],model='GPT-6.1 Sol',config_id=CONFIG_ID,completed_tasks=40,
                mean_reward=mean,full_score_count=sum(r['official_reward']==1 for r in rows),partial_score_count=sum(0<r['official_reward']<1 for r in rows),
                zero_score_count=sum(r['official_reward']==0 for r in rows),exception_count=1,full_score_rate=sum(r['official_reward']==1 for r in rows)/40,
                positive_reward_rate=sum(r['official_reward']>0 for r in rows)/40,totals=sums,mean_agent_elapsed_sec=sums['agent_elapsed_sec']/40,
                median_agent_elapsed_sec=statistics.median(r['agent_elapsed_sec'] for r in rows),
                observed_generation_responses=len(calls),reported_reasoning_tokens=sum(c['reasoning_tokens'] or 0 for c in calls),
                provider_usage_cost_available=any(c['provider_usage_usd'] is not None for c in calls),
                reported_upstream_providers=list({c['upstream_provider'] for c in calls if c['upstream_provider']}),
                top_cost_tasks=[dict(task_id=r['task_id'],reward=r['official_reward'],cost_usd=r['harbor_total_usd'],cost_share=r['harbor_total_usd']/sums['harbor_total_usd'],turns=r['agent_turns']) for r in top[:3]],
                original_started_local=job['started_at'],finished_local=job['finished_at'],timezone='Asia/Shanghai; original naive job timestamps are local, trial timestamps retain UTC offsets',
                interrupted_before_agent_calls=2,versions=versions,rows=rows,excluded_attempts=excluded,
                taskset_sha256=hashlib.sha256((ROOT/'config/tasks40_approved.txt').read_bytes()).hexdigest(),
                checks=dict(unique_tasks=40,all_rewards_present=True,original_23_hashes_unchanged=True,call_tokens_reconcile_per_trial=True,job_totals_reconcile=True,
                            provider_usage_usd='not returned',actual_upstream_route='not returned in saved responses',actual_subscription_cash_charge='not available'))
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv('逐题结果_40题.csv',rows);write_csv('逐调用用量.csv',calls);write_csv('中断与替换记录.csv',excluded)
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','excluded_attempts']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
