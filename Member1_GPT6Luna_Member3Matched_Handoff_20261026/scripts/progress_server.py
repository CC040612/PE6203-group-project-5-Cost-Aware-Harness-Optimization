#!/usr/bin/env python3
"""Local-only live progress page for Member 1 baseline runs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
JOB_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")

PAGE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Member 1 实验实时进度</title><style>
body{font:16px system-ui,"Microsoft YaHei",sans-serif;background:#101318;color:#e8edf4;margin:0;padding:28px}
main{max-width:920px;margin:auto}.card{background:#1a2029;border:1px solid #303947;border-radius:14px;padding:22px;margin:14px 0}
h1{font-size:24px;margin:4px 0 16px}.muted{color:#aab6c5;font-size:14px;word-break:break-all}
.row{display:flex;gap:14px;flex-wrap:wrap}.metric{flex:1;min-width:150px;background:#111720;border-radius:10px;padding:16px}
.value{font-size:24px;font-weight:700;margin-top:5px}.bar{height:12px;background:#343d4b;border-radius:8px;overflow:hidden;margin:16px 0 8px}
.fill{height:100%;width:0;background:linear-gradient(90deg,#20c997,#78e08f);transition:width .3s}
.status{font-weight:700}.ok{color:#75e0a2}.bad{color:#ff8181}.warn{color:#ffd37a}
table{width:100%;border-collapse:collapse;margin-top:10px}th,td{text-align:left;padding:9px;border-bottom:1px solid #303947;font-size:14px}th{color:#aab6c5}
@media(max-width:600px){body{padding:14px}.card{padding:16px}}
</style></head><body><main><h1>Member 1 · GPT-6 Luna baseline</h1>
<div class="muted" id="job"></div><section class="card"><div class="row">
<div class="metric">运行状态<div class="value status" id="status">读取中…</div></div>
<div class="metric">完成题目<div class="value" id="count">—</div></div>
<div class="metric">成功 / 错误<div class="value" id="outcomes">—</div></div>
<div class="metric">运行时间<div class="value" id="elapsed">—</div></div>
<div class="metric">当前题目<div class="value" id="current">—</div></div></div>
<div class="bar"><div class="fill" id="fill"></div></div><div class="muted" id="updated"></div></section>
<section class="card"><b>本轮配置</b><p id="config" class="muted">读取中…</p></section>
<section class="card"><b>已完成题目</b><table><thead><tr><th>题目</th><th>结果</th><th>异常类型</th></tr></thead><tbody id="trials"></tbody></table><p id="empty" class="muted">等待首题结果…</p></section>
<p class="muted">页面每 5 秒刷新；关闭页面不会停止实验。本页仅本机可访问。</p></main>
<script>
const job=location.pathname.split('/').filter(Boolean).pop();
document.getElementById('job').textContent='运行编号：'+job;
function duration(seconds){seconds=Math.max(0,Math.floor(seconds||0));let h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return h+'小时 '+m+'分 '+s+'秒'}
async function refresh(){try{const r=await fetch('/api/jobs/'+encodeURIComponent(job),{cache:'no-store'});if(!r.ok)throw Error('状态读取失败：HTTP '+r.status);const d=await r.json();
const done=d.completed||0,total=d.planned||0,ok=d.successes||0,err=d.errors||0;
document.getElementById('status').textContent=d.status||'未知';document.getElementById('status').className='value status '+(String(d.status).includes('fault')||String(d.status).includes('error')?'bad':String(d.status)==='running'?'ok':'');
document.getElementById('count').textContent=done+' / '+total;document.getElementById('outcomes').textContent=ok+' / '+err;
document.getElementById('fill').style.width=(total?Math.min(100,done*100/total):0)+'%';
document.getElementById('elapsed').textContent=duration(d.elapsed_seconds);document.getElementById('updated').textContent='最近更新：'+(d.updated_local||'—');
document.getElementById('current').textContent=(d.current_task&&d.current_task.name)||'等待中';
document.getElementById('config').textContent=[d.model||'', 'temperature='+d.temperature, 'max_tokens='+d.max_tokens, 'reasoning_effort 未发送', '并发='+d.concurrency, '自动重跑='+ (d.automatic_reruns?'开启':'关闭')].join(' · ');
const body=document.getElementById('trials');body.replaceChildren();for(const t of d.trials||[]){const tr=document.createElement('tr');for(const v of [t.trial,t.exception_type?'错误':(t.reward===null?'无评分':'完成 · reward '+t.reward),t.exception_type||'—']){const td=document.createElement('td');td.textContent=v;tr.append(td)}body.append(tr)}document.getElementById('empty').hidden=(d.trials||[]).length>0;
}catch(e){document.getElementById('status').textContent=e.message;document.getElementById('status').className='value status bad'}}
refresh();setInterval(refresh,5000);
</script></body></html>'''


def payload(job: str) -> dict:
    state_path = ROOT / "logs" / f"{job}_state.json"
    if not state_path.is_file():
        raise FileNotFoundError
    state = json.loads(state_path.read_text(encoding="utf-8"))
    config = {}
    raw_config_path = state.get("config", "")
    if re.match(r"^/mnt/[a-z]/", raw_config_path, re.I):
        drive = raw_config_path[5].upper()
        cfg_path = Path(drive + ":\\" + raw_config_path[7:].replace("/", "\\"))
    else:
        cfg_path = Path(raw_config_path)
    if cfg_path.is_file():
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    trials = state.get("trial_summaries", [])
    successes = sum(t.get("exception_type") is None and t.get("rewards") is not None for t in trials)
    errors = sum(t.get("exception_type") is not None for t in trials)
    started = state.get("started_utc")
    elapsed = 0
    if started:
        from datetime import datetime, timezone
        elapsed = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()))
    kwargs = ((config.get("agents") or [{}])[0].get("kwargs") or {})
    return {
        "status": state.get("status"), "planned": state.get("planned_trials", 0),
        "completed": state.get("completed_trial_results", len(trials)), "successes": successes,
        "errors": errors, "trials": [{"trial": t.get("trial", ""), "reward": (t.get("rewards") or {}).get("reward"), "exception_type": t.get("exception_type")} for t in trials],
        "started_utc": started, "elapsed_seconds": elapsed, "current_task": state.get("current_task"),
        "updated_local": state.get("updated_utc"), "automatic_reruns": state.get("automatic_reruns", False),
        "model": (config.get("agents") or [{}])[0].get("model_name", ""),
        "temperature": kwargs.get("temperature"), "max_tokens": (kwargs.get("llm_kwargs") or {}).get("max_tokens"),
        "concurrency": config.get("n_concurrent_trials"),
    }


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        api = path.startswith("/api/jobs/")
        prefix = "/api/jobs/" if api else "/jobs/"
        job = path[len(prefix):] if path.startswith(prefix) else ""
        if not JOB_RE.fullmatch(job):
            return self.send_body(404, "text/plain; charset=utf-8", b"Not found")
        if api:
            try:
                body = json.dumps(payload(job), ensure_ascii=False).encode("utf-8")
                return self.send_body(200, "application/json; charset=utf-8", body)
            except FileNotFoundError:
                return self.send_body(404, "application/json; charset=utf-8", b'{"error":"job not found"}')
            except Exception as exc:
                body = json.dumps({"error": type(exc).__name__}).encode()
                return self.send_body(500, "application/json; charset=utf-8", body)
        return self.send_body(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print("Member 1 progress page listening on http://127.0.0.1:8766", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
