# Member 3：重复失败检测与恢复

## 改进内容

在 Terminus-2 上增加循环恢复机制：
当单条命令连续出现三次相同的错误输出时，
向下一轮模型反馈添加恢复提示，并记录 JSONL 事件。
默认最多干预两次，支持关闭改进进行对照。

本机制基于命令和错误文本判断，不等同于可靠的退出码检测。
它不增加独立模型调用，但提示及后续上下文仍会消耗 token。

## 文件

- loop_recovery.py：检测器与自定义 agent
- test_*.py：单元和集成测试
- smoke_api.py：手动 API 接入测试
- scripts/run_smoke.sh：官方任务接入试跑
- validation/unittest.txt：测试结果
- notes/：调试记录与失败分析
- runs/smoke/：Harbor 原始试跑结果

## 环境

在 TUA-Bench 仓库根目录执行：

    uv sync --locked --python /usr/bin/python3

已验证 Python 3.12.3、Harbor 0.6.3、Docker 29.8.2。
使用仓库中的 uv.lock 固定依赖。

## 测试

    uv run --locked python -m unittest discover -s member3 -p 'test_*.py' -v

当前 9 项测试通过。
受控测试模拟终端会话，不证明官方任务成功率提升。

## 模型连接

密钥通过环境变量 OPENAI_API_KEY 提供，不写入代码。
OPENAI_BASE_URL 可覆盖 smoke_api.py 的默认地址。

当前本机 WSL 转发地址：

    http://172.26.240.1:64915/v1

这是本机环境地址，其他机器需要自行配置；
WSL 重启后地址也可能变化。

手动接入测试：

    uv run --locked python -m member3.smoke_api

## 官方任务试跑

    bash member3/scripts/run_smoke.sh

配置：gpt-6-luna、循环恢复开启、最多 10 轮、
单次输出上限 2048 token、并发 1、尝试 1 次。

此脚本用于接入调试，不是默认设置 baseline，
也不是最终正式实验配置。

## 当前结果与限制

任务 010-pivot-product-revenue：
官方 reward=0，无程序异常，执行 7 轮。
输入 24576 token，输出 2444 token，缓存 0。
未记录循环恢复事件。

轨迹显示模型使用 SUMIF 汇总，
而官方评估要求 Pivot Table 结构。

Harbor 报告 cost_usd=0.0036796；
价格来源尚未核实，不视为 Plus 实际扣费。
Plus 配额及参考美元成本的报告方式尚待课程方确认。

尚未完成固定至少 40 个任务上的正式对照实验。
