# Member 1 · GPT-6 Luna（Member 3 参数匹配）实验交接

整理时间：2026-10-26（北京时间）  
最终运行段：gpt6luna-member3-matched-baseline-resilient-20261025T164947Z  
最终运行段状态：finished_with_task_errors，19/19 个任务均已记录结果或超时。

## 结论摘要

- 目标题目：已批准的 40 题，每题最多保留一个正式评分结果。
- 最终可评分题：36/40；未取得评分的题：4 题。
- 36 个有分数结果的 reward 总和：15.8703461663；均值：0.4408429491。均值只对这 36 题计算，不能当作完整 40 题均值。
- 未评分题：089-install-recommended-exts（两次均取消）、092-fix-tetris-bug（控制器切换时取消）、100-name-mountain-photos 和 111-set-video-wallpaper（单题 40 分钟硬超时）。
- 100 与 111 的逐题子进程在控制器强制超时后未能自行写终态状态文件；它们的子状态快照可能仍显示 running。最终控制器状态和 final_task_results.csv 已将它们记为 TaskTimeoutError，后两者是汇总依据。
- 账号/API 早期故障后来通过更换账号解决；最终 resilient 运行段的 19 题中，17 题有评分，2 题超时，控制器完成后续题目。
- 全部尝试共留下 45 条 trial 结果记录，对应 40 个不同题目；早期失败和取消尝试均保留在原始日志中。reports/final_task_results.csv 按题目汇总最终采用的评分或未评分原因。

## 实验参数

| 参数 | 实际设置 |
|---|---|
| 模型 | openai/gpt-6-luna |
| temperature | 0.7 |
| max_tokens | 2048 |
| reasoning_effort | 未发送 |
| 模型输入上限元数据 | 272000 |
| 模型输出上限元数据 | 2048 |
| 并发 | 1 |
| 每题尝试数 | 1，不自动重跑 |
| 单题硬超时 | 2400 秒 |
| API Base | 本机 Cockpit 桥接地址 http://127.0.0.1:58429/v1 |

参数取自 Member 3 的运行配置与调试记录。API Base 是本机地址；同学在其他电脑上不能直接使用它。交接包不含 API 密钥、账号令牌或 cockpit-local.env。

## 运行过程及中断记录

| 运行段 | 结果 |
|---|---|
| ...formal-20261025T113533Z | 2 条记录后因 ServiceUnavailableError: No compatible account is available for this model 停止；没有评分。 |
| ...formal-rerun-20261025T115523Z | 前 4 题获得评分；052 请求时认证令牌过期，守护脚本停止该段。 |
| ...formal-continue-20261025T122500Z | 14 题获得评分；状态文件原子替换触发 PermissionError，监控脚本异常退出；089 记为取消。 |
| ...formal-resume-20261025T155552Z | 089 的 Chrome 扩展安装任务在环境缺少 root-owned sandbox helper、没有 sudo 的情况下反复尝试；为避免继续空耗，停止并记录取消。 |
| ...formal-resume-20261025T164228Z | 091 得到评分；切换到逐题控制器期间 092 被取消，原始记录保留。 |
| ...resilient-20261025T164947Z | 从 093 起逐题隔离运行 19 题；API/任务错误记录后跳过，100、111 在 2400 秒硬超时后标记无评分，其余任务完成。最终状态 finished_with_task_errors。 |

详细状态、异常类型、时间戳和每题 reward 在 logs/ 与 reports/final_task_results.csv。原始 trial.log、result.json、trajectory.json 和附件都在 raw/raw_jobs.tar.gz。

## Token 用量

已汇总 42 份原始 trajectory，并另加一次最小 API 连通性试请求（10 prompt tokens、5 completion tokens）：

- Prompt tokens：40,467,089
- Completion tokens：285,543
- 其中缓存 prompt tokens：34,704,896

此数包含不同运行段、失败/取消尝试以及长时间卡循环产生的记录，不是只统计 40 个最终题目结果。没有生成 trajectory 的失败请求，其上游计费使用量无法从本机日志核实；本机网关也没有提供可信的金额账单，因此费用标为未知。

## 推荐查看顺序

1. reports/final_task_results.csv：40 题最终汇总。
2. reports/summary_stats.json：题数、reward 与 token 汇总。
3. reports/token_usage.json：按运行段拆分的 trajectory token 明细与统计口径。
4. configs/：每个运行段的配置和元数据；逐题运行配置也一并保留。
5. logs/：每段状态、控制台日志和 resilient 控制器日志。
6. raw/raw_jobs.tar.gz：Harbor 原始任务目录、完整轨迹、结果和任务附件。
7. scripts/：配置、执行、逐题跳过控制器、token 汇总和原始日志归档脚本。

## 执行命令记录

最终逐题控制器运行形式：

    wsl -d Ubuntu-24.04 -- python3 \
      '/mnt/d/夏嫣然/6203/group project/member1/scripts/resilient_run.py' \
      '/mnt/d/夏嫣然/6203/group project/member1/config/generated/gpt6luna-member3-matched-baseline-resilient-20261025T164947Z.json'

控制器为每题生成单题配置，通过 run_baseline.sh formal run 启动，最多运行 2400 秒；题目返回异常或超时后保留记录、不重跑并进入下一题。控制器不会恢复因电脑关机、WSL 被关闭或系统掉电而中断的进程。

## 文件完整性与限制

- raw_jobs.tar.gz 保存实验原始产物；压缩包内路径以 /home/member2/experiments/member1/jobs/ 下的运行段为根。
- 报告中的 reward 是 Harbor verifier 结果，不等同于成功率。
- 本交接包不包含 API 凭据、私密 .env 文件或可用于登录账号的令牌。
