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

# PE6203 Group Project 5: Cost-Aware Harness Optimization

This repository contains the deliverables and project codebase contributed by group members (Member 1, Member 2, and Member 3).

---

## 📂 Project Structure & Deliverables

- **`Member1_.../`**: Contains Member 1's experimental code, baseline implementations, and handoff documentation.
- **`member2/`**: Contains Member 2's pipeline components, provenance tracking, and results data.
- **`member3/`**: Contains Member 3's code framework and configuration files. *(Note: Due to GitHub's individual file size limit of 100 MB, Member 3's large backup datasets/archives are hosted externally; see details below).*

---

## 🔗 Member 3 Large Files / Backups (Google Drive)

Due to GitHub's 100 MB file size restriction, Member 3's heavy backup archive (`.tar.gz`) cannot be stored directly in this repository. 

You can access and download Member 3's full backup files via the Google Drive link below:
👉 **[Member 3 Google Drive Backup Link](https://drive.google.com/drive/folders/1bnT5GMjU-AJYVaadGYep-IYZGY4D6sb6?usp=drive_link)**

---

# 项目说明文档（中文对照）

# PE6203 小组项目 5：成本感知测试框架优化

本仓库包含了小组成员（Member 1、Member 2 和 Member 3）各自的交付物与项目代码。

---

## 📂 项目结构与交付物

- **`Member1_.../`**: 包含 Member 1 的实验代码、基线实现以及交接文档。
- **`member2/`**: 包含 Member 2 的流水线组件、来源追踪及运行结果数据。
- **`member3/`**: 包含 Member 3 的代码框架与配置文件。*（注：由于 GitHub 单个文件 100MB 的大小限制，Member 3 的大容量备份数据集/压缩包已存放在外部，详情见下方）。*

---

## 🔗 Member 3 大文件备份（谷歌网盘）

由于超过了 GitHub 的文件大小限制（100MB），Member 3 的完整大型备份压缩包无法直接上传至本仓库。

你可以通过以下 Google Drive 链接访问并下载 Member 3 的所有备份文件：
👉 **[Member 3 谷歌网盘备份链接](https://drive.google.com/drive/folders/1bnT5GMjU-AJYVaadGYep-IYZGY4D6sb6?usp=drive_link)**
