"""Write the final explanation and shareable archive from saved files only."""
import csv
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/01a1575c-2b59-7890-b137-02d160ed18ec'
NAME = 'gpt61sol-cockpit-formal-20261021-231816-860550'
JOB = Path('/home/member2/experiments/jobs')/NAME
INCIDENT = Path('/home/member2/experiments/incidents/20261022-0058')


def main():
    d=json.loads((OUT/'analysis.json').read_text());s=d['totals'];top=d['top_cost_tasks'][0]
    # This reconstructs the recorded Harbor total, not a subscription bill.
    reconstructed=(s['prompt_tokens']-s['cached_tokens'])*2e-6+s['cached_tokens']*0.1e-6+s['completion_tokens']*10e-6
    assert abs(reconstructed-s['harbor_total_usd'])<1e-8
    snapshot={'basis':'Rates reconstruct the observed Harbor/LiteLLM estimate; not actual subscription billing',
              'observed_run_date':'2026-10-21/22','input_noncache_usd_per_million':2,'cache_read_usd_per_million':0.1,
              'output_usd_per_million':10,'reconstructed_total_usd':reconstructed,'actual_cash_charge_usd':None,
              'provider_usage_cost_returned':False,'long_context_tier_applied':'not evidenced by aggregate reconstruction'}
    (OUT/'费用口径快照.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    table='\n'.join(f"| {i+1} | {r['task_id']} | {r['official_reward']:.6f} | {r['score_category']} | {r['agent_elapsed_sec']:.2f} | {r['harbor_total_usd']:.6f} |" for i,r in enumerate(d['rows']))
    report=f'''# 成员2：GPT-6.1 Sol正式第一轮最终结果

组内批准的固定40题已经全部完成，结束时间为2026年10月22日11:19:52（北京时间）。以下是成员2的强模型baseline结果，使用原版Terminus-2；尚未包含其他成员的Qwen或改进版数据。

## 最终成绩

| 指标 | 结果 | 定义 |
| --- | ---: | --- |
| 有官方评分的任务 | 40/40 | 所有预定任务均计入，不剔除失败 |
| 平均官方reward（主指标） | **{d['mean_reward']:.6f}，即{d['mean_reward']:.2%}** | 40题reward的算术平均 |
| 满分题数 | 18题 | reward=1 |
| 满分题比例（辅助指标） | 45.00% | 18/40 |
| 部分得分题数 | 5题 | 0<reward<1 |
| 零分题数 | 17题 | reward=0，包含088题超时 |
| 最终异常 | 1题 | 088题AgentTimeoutError，按官方reward=0保留 |

**55.10%是平均评分，45.00%是满分题比例。报告中不要把55.10%直接写成“满分成功率”。** 另有23题reward>0，比例57.50%，只能称“获得非零评分的比例”。

## 方法与实验设置

使用组内提供的tasks40_approved.txt原样40题，名单SHA256：`{d['taskset_sha256']}`。模型完整配置名为`openai/gpt-6.1-sol`，通过Cockpit本地网关和用户自己的Plus授权接入；保存的736份响应均可按response_id关联，实际上游路由没有在这些响应中返回。

配置标识：`{d['config_id']}`。原版Terminus-2 2.0.0，每题1次正式评分，并发2；Agent时间上限2400秒，timeout_multiplier和agent_timeout_multiplier均为1.0；max_turns未显式覆盖，费用上限未配置。reasoning_effort=medium，temperature=null（不发送不兼容的temperature采样参数）。A/B改进均未启用；使用组内原样提供的日志权限适配器。

TUA-Bench commit：`{d['versions']['tua_commit']}`；Harbor {d['versions']['harbor']}；Python {d['versions']['python']}；LiteLLM {d['versions']['litellm']}；OpenAI SDK {d['versions']['openai']}。依赖锁文件、运行配置、适配器、任务名单和运行入口均随交接包提供。

## 用量与费用

| 指标 | 本轮合计 |
| --- | ---: |
| 输入token | {s['prompt_tokens']:,} |
| 其中缓存token | {s['cached_tokens']:,} |
| 输出token | {s['completion_tokens']:,} |
| 其中响应返回的reasoning token | {d['reported_reasoning_tokens']:,} |
| 已返回且去重的生成响应 | {d['observed_generation_responses']:,}份 |
| 主循环轮次（n_episodes） | {s['agent_turns']:,} |
| trajectory中的命令调用数 | {s['command_count']:,} |
| Harbor API等价估算 | **${s['harbor_total_usd']:.4f}** |
| 平均每题API等价估算 | ${s['harbor_total_usd']/40:.4f} |
| Agent累计执行时间 | {s['agent_elapsed_sec']:.2f}秒 |
| 平均每题Agent执行时间 | {d['mean_agent_elapsed_sec']:.2f}秒 |
| Agent执行时间中位数 | {d['median_agent_elapsed_sec']:.2f}秒 |

缓存是输入token的子集，推理token是输出的子集，不得再次相加。737轮中包含088题最后一次未返回响应的轮次，因此不应把轮次数当作736份成功返回的响应数。

**${s['harbor_total_usd']:.4f}不是Plus实际扣款。** Harbor的金额可由本轮记录反算为：非缓存输入$2/百万token、缓存输入$0.10/百万token、输出$10/百万token。服务商usage.cost、实际订阅现金费用及各请求的官方授权/回退路由未获得，不以0替代，也不将估算当实际账单。与Qwen/OpenRouter比较时，所有配置应统一使用可比的API等价估算，或另列实际费用；不能混用。

40题的默认摘要次数全部为0，没有成员3式新增自检或恢复调用；本轮可识别的included harness overhead为0。Job层max_retries=0不代表API内部完全无重试；网关隐藏重试未独立计数。逐调用CSV保存了用途、费用是否已包含及response_id，避免重复加总。

Agent累计耗时是40题的执行时长之和，包含并发重叠。23:19到次日11:19的整段时钟跨度含夜间暂停，不能作为模型连续运行12小时的证据。各题同时保留Agent起止UTC与整次trial耗时。

## 结果解释与典型案例

1. **主要成本集中在失败循环。** 088-extract-presenter-photos的reward=0，n_episodes=383，API等价估算${top['cost_usd']:.4f}，占本轮{top['cost_share']:.2%}。轨迹显示模型因照片中的人脸身份匹配而反复拒绝继续，末段持续返回空commands且task_complete=false，直到2400秒超时。它是原版harness在未取得新信息时仍持续请求模型的案例，支持将“重复/停滞检测与合理终止”作为待检验的改进方向；本轮没有证明该改进的实际收益。
2. **成功任务也有不同成本。** 038-zurich-rental-car得到1分，主循环41轮、估算$1.2608；106-create-charles-ssh-user同样1分，仅4轮、估算$0.0156。因此仅看总成功数不足以评估效率，还应比较每题轨迹和费用。
3. **官方评分存在部分得分。** 070、074、076、081、112分别获得约0.9073、0.7331、0.8440、0.8035、0.7506。保留连续reward，不能把所有非零分一律当满分，也不能简单将部分得分归零。
4. 其他16个零分任务没有最终结构化异常。现有空的验证器stdout不能给出全部失败原因；不把它们统一归因于“API报错”或模型能力不足。逐题归因应结合归档轨迹、任务要求与产物继续核查。

## 中断与恢复说明

凌晨00:58，监督脚本误将088题超时堆栈中的Python“line 401”及LiteLLM文本识别为接口故障，发出中断。原23份已有评分的result.json在恢复前后SHA256完全一致，正常失败及088超时均未重跑。

099和100当时处于容器准备阶段；原结果中的agent_execution均为空，agent目录没有生成响应或轨迹记录。两份旧尝试完整保留，selected_for_evaluation=false、official_reward=null，不能当作0分加入均值，也不能把缺失费用填成0。修复监督脚本后，于10:32按同一配置恢复17题。恢复后的099得到1分，100得到0分。原始旧trial、新trial及UUID对应关系均在中断CSV与recovery.json中。

因此可描述为“40个任务各保留1次正式评分，另存2次环境准备中断记录”，不能声称没有发生任何任务重新启动。当前证据未证明此次暂停由额度耗尽导致。

## 可以直接交给Report/PPT负责人的英文结果段落

Using the original Terminus-2 harness, GPT-6.1 Sol was evaluated once on the group's fixed 40-task subset of TUA-Bench. The mean official reward was **0.5510**, with **18 full-score tasks, 5 partially scored tasks, and 17 zero-score tasks**. The full-score task rate was **45.0%**. The run recorded **10,013,015 input tokens** (including 4,954,752 cached tokens) and **94,744 output tokens**, with a Harbor API-equivalent cost estimate of **US$11.5594**, or **US$0.2890 per task**. These estimates do not represent observed Plus subscription cash charges. One task reached the 2,400-second agent timeout and remained in the evaluation with reward zero. It accounted for 53.36% of the estimated cost after repeatedly returning no actionable commands. Two earlier attempts were interrupted during environment preparation, before agent execution; they were retained separately and excluded from scoring. This single-run baseline cannot establish variability or the benefit of a harness modification without the other configurations.

## 给成员4的使用说明

先使用Excel“结果汇总”查看主指标，再用“逐题结果_40题.csv”关联其他配置。“逐调用用量.csv”含736份去重响应的用量；“中断与替换记录.csv”单独登记2份旧尝试。原始job配置、结果、轨迹、逐次响应、验证器及产物在交接ZIP的raw目录。价格和字段缺失口径另见“成员4字段核对.md”。

当前尚无其他成员配置的数据，因此本材料没有制作跨模型准确率—成本比较、Pareto结论或改进消融结论。需要成员1、3、4的数据才能完成这些全组结论。只运行了一轮，不宣称已经估计重复运行方差或可重复稳定性。

## 40题明细

| 序号 | 任务 | 官方reward | 类别 | Agent耗时（秒） | API等价估算（USD） |
| ---: | --- | ---: | --- | ---: | ---: |
{table}
'''
    (OUT/'最终结果说明.md').write_text(report,encoding='utf-8')
    audit='''# 成员4字段核对

按《记录要求(1).xlsx》第一列逐项核对，以下是本轮交接现状。完整机器字段在CSV，原始证据在归档raw目录。

| 要求 | 本轮记录与缺口 |
| --- | --- |
| config_id、stage、job/trial身份 | 全部记录；正式数据与历史单句测试、基础设施nop检查分开 |
| task_id/checksum、replicate_index | 40题唯一且与批准名单一致，均为slot 1 |
| selected_for_evaluation、reward | 40条选入且评分完整；两条环境准备中断不选入，reward为空 |
| 状态、异常、停止原因 | 39条无最终结构化异常；1条Agent超时；另两条CancelledError有原因及替换映射。普通任务的停止原因按轨迹自报完成或返回评分记录，不据零分猜测原因 |
| Agent/整次trial原始起止时间与耗时 | 逐题CSV保留UTC时间、Agent秒数和整次trial秒数；中断原始起止在归档result.json |
| Agent轮次、命令数 | n_episodes与trajectory命令数分别记录；不使用trajectory节点总数代替主循环轮次 |
| 输入、缓存、输出、推理token | 每份响应按ID去重；逐调用合计与每份AgentResult和job合计一致。推理token仅采用网关返回值 |
| harbor_total_usd | 40条全部有值；这是API等价估算 |
| provider_usage_usd | 原始响应未返回usage.cost，留空；不能填写为0 |
| inference / included_overhead | 本轮默认摘要次数均为0，所有已记录调用为推理；总额不再另加摘要费 |
| additional_unincluded_usd | 没有自定义新增模型调用，记录为0；不是用0代替缺失服务商账单 |
| billing_status、price_snapshot | 明确为估算；费用口径快照记录可重建Harbor总额的费率。实际Plus现金扣款未获得 |
| upstream_provider、response_id | 响应ID全部保留；upstream_provider及实际官方/回退路由未返回，留空。配置provider=openai不作为已核验上游证据 |
| A/B开关与触发记录 | 均关闭；这是原版baseline，无改进触发事件 |
| retry层级及replacement | Job重试上限0；两次基础设施中断有新旧trial UUID及名称。内部API重试保留，网关隐藏重试次数无独立证据 |
| 版本、配置、完整命令、依赖锁 | 原job lock保留启动命令；uv.lock、固定commit、各库版本、运行入口、原配置及恢复配置不变证据均提供。脚本内机器路径需按复现机器调整 |
| timeout / max_turns / cost_budget | 时间2400秒，max_turns沿用原版无显式覆盖；美元费用上限未配置。不能写成已经执行了统一固定美元上限 |
| call_type / included_in_trial_total | 逐调用CSV已标记inference与已包含；默认摘要0次 |
| error / rerun理由及替换ID | 旧CancelledError、监控误判依据、088超时和新旧映射完整保留；不选择性重跑低分任务 |
| 完整原始日志 | 交接ZIP的raw/job和raw/incident；包含完整trajectory、逐调用debug原始响应、verifier与产物。分享副本隐藏认证密钥字段，原文件未修改 |

尚缺的服务商实际usage费用、实际订阅扣款、逐请求真实上游路由，不是从Harbor日志可以推算出的事实。若全组需要这些口径，须另向网关历史或账户账单取证。现有结果适合按统一API等价估算口径比较，不能将其与其他配置真实账单直接混画。
'''
    (OUT/'成员4字段核对.md').write_text(audit,encoding='utf-8')
    # Export only explicit artifacts and experiment files. Never include .env/account data.
    selected=[p for p in OUT.iterdir() if p.is_file() and p.suffix in ('.xlsx','.csv','.md','.json') and not p.name.startswith('build')]
    files=[(p,'results/'+p.name) for p in selected]
    for p in JOB.rglob('*'):
        if p.is_file():files.append((p,'raw/job/'+p.relative_to(JOB).as_posix()))
    for p in INCIDENT.rglob('*'):
        if p.is_file():files.append((p,'raw/incident/'+p.relative_to(INCIDENT).as_posix()))
    for p in (ROOT/'results/incident-20261022-0058').iterdir():
        if p.is_file():files.append((p,'provenance/incident/'+p.name))
    for name in ['config/tasks40_approved.txt','config/tasks40_for_group.md','config/generated/'+NAME+'.json',
                 'config/generated/'+NAME+'.meta.json','config/active-formal-run.json','adapters/log_permissions_env.py',
                 'scripts/run_cockpit_baseline.sh','scripts/prepare_baseline_run.py','scripts/guard_formal_run.py',
                 'scripts/check_guard_faults.py','scripts/cockpit_wsl_bridge.py','scripts/cockpit_windows_pipe.py',
                 'scripts/prepare_interruption_recovery.py','scripts/summarize_final_run.py','scripts/package_final_results.py']:
        p=ROOT/name;files.append((p,'provenance/'+name))
    files.append((Path('/home/member2/TUA-Bench/uv.lock'),'provenance/uv.lock'))
    # Local gateway key is read privately solely to remove it from sharing copies.
    secret_values=[]
    for line in (ROOT/'config/cockpit-local.env').read_text().splitlines():
        if line.startswith('OPENAI_API_KEY='):secret_values.append(line.split('=',1)[1].strip().strip('"\'' ).encode())
    token_pattern=re.compile(rb'(?:agt_codex_[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9_-]{20,})')
    sensitive={'api_key','api_key_sha256','authorization','azure_ad_token','azure_password','client_secret','access_token','refresh_token'}
    redaction_fields=0
    def scrub(value):
        nonlocal redaction_fields
        if isinstance(value,dict):
            result={}
            for k,v in value.items():
                if k.lower() in sensitive and v:
                    result[k]='[REDACTED]';redaction_fields+=1
                else:result[k]=scrub(v)
            return result
        if isinstance(value,list):return [scrub(v) for v in value]
        return value
    manifest=[]
    target=OUT/'成员2_GPT61Sol_完整结果交接.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,arc in files:
            raw=p.read_bytes();original_hash=hashlib.sha256(raw).hexdigest()
            if p.suffix=='.json':
                try:raw=json.dumps(scrub(json.loads(raw)),ensure_ascii=False,indent=2).encode()
                except (ValueError,UnicodeDecodeError):pass
            for secret in secret_values:
                if secret:raw=raw.replace(secret,b'[REDACTED]')
            raw=token_pattern.sub(b'[REDACTED]',raw)
            assert not token_pattern.search(raw)
            assert all(not secret or secret not in raw for secret in secret_values)
            z.writestr(arc,raw)
            manifest.append({'path':arc,'original_sha256':original_hash,'export_sha256':hashlib.sha256(raw).hexdigest(),'export_bytes':len(raw)})
        z.writestr('MANIFEST.json',json.dumps({'job_name':NAME,'created_utc':datetime.now(timezone.utc).isoformat(),
                    'files':manifest,'redacted_secret_fields':redaction_fields,'note':'Sharing copies have credentials redacted; original experiment files are unchanged.'},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for info in z.infolist():
            assert not info.filename.endswith('.env')
            raw=z.read(info)
            assert not token_pattern.search(raw)
            assert all(not secret or secret not in raw for secret in secret_values)
    print(json.dumps({'archive':str(target),'files':len(manifest),'zip_bytes':target.stat().st_size,'secret_fields_redacted':redaction_fields,'archive_integrity':'passed','credential_scan':'passed'},ensure_ascii=False))


if __name__=='__main__':main()
