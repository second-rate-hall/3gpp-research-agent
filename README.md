# 3GPP Research Agent

`3gpp-research-agent` 是“路线二：自建 3GPP 专用 Agent”的可运行实现。它不是网页聊天入口，也不是工作流模板，而是一个面向 3GPP 标准研究的 CLI Agent：用户输入研究议题后，Agent 自动规划研究范围、下载官方 3GPP 资料、解析文档、建立本地检索库、检索证据，并调用 NVIDIA NIM 生成带证据表和核验状态的深度研究报告。

## 与 3gpp-research-kit 的关系

`3gpp-research-kit` 是可独立使用的研究工作台、Codex skill 和证据工具层；`3gpp-research-agent` 是路线二的产品化 CLI Agent。两者的长期分工是：

- `3gpp-research-kit` 负责通用证据能力：下载、解析、索引、检索、关系表、报告模板和证据核验。
- `3gpp-research-agent` 负责专用 Agent 能力：Planner、模型调用、多阶段报告生成、专项报告器、运行记录和 CLI 体验。

当前实现为了保证 `3gpp-research-agent` 可独立运行，仍内置了一套轻量 evidence store（`agent3gpp/store.py`）。后续工程化方向是逐步把这部分收敛为对 `3gpp-research-kit` 的调用，避免两套资料处理和证据核验逻辑长期分叉。

## 目标

```text
user topic
-> Planner 生成研究计划、候选规范、检索 query、比较轴和核验问题
-> 自动下载官方 3GPP specification archive
-> 解析 ZIP / DOCX / TXT / HTML / CSV / optional PDF
-> 建立 SQLite FTS evidence database
-> 按计划执行多 query 证据检索和关系抽取
-> Report Writer / Verifier 生成深度研究报告
-> 默认保存到 runs/
```

## 安全提示

不要把真实 API key 写进 README、代码或 Git。请使用环境变量或本地 `.env`。

```bash
copy .env.example .env
```

编辑 `.env`：

```text
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=deepseek-ai/deepseek-v4-flash
```

可选：为 Planner 和 Writer 分别指定模型。

```text
NVIDIA_PLANNER_MODEL=qwen/qwen3.5-122b-a10b
NVIDIA_WRITER_MODEL=deepseek-ai/deepseek-v4-flash
```

NVIDIA NIM for LLMs 提供 OpenAI-compatible `/v1/chat/completions` endpoint。本项目默认使用 `https://integrate.api.nvidia.com/v1`。

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

如需 PDF 解析：

```bash
pip install -e ".[pdf]"
```

## 快速使用

最简单的方式：只输入研究议题。

```bash
python -m agent3gpp "请分析4G和5G在RRC re-establishment流程的异同"
```

等价显式命令：

```bash
python -m agent3gpp research "请分析4G和5G在RRC re-establishment流程的异同"
```

报告默认保存到 `runs/`。如果只想打印、不保存：

```bash
python -m agent3gpp research "请分析4G和5G在RRC re-establishment流程的异同" --no-save
```

查看 Planner 生成的研究计划：

```bash
python -m agent3gpp plan "请分析4G和5G在RRC re-establishment流程的异同"
```

手动下载、解析、检索：

```bash
python -m agent3gpp fetch-spec --spec 38.331
python -m agent3gpp parse
python -m agent3gpp search RRCReestablishment --limit 5
```

专利背景辅助分析：

```bash
python -m agent3gpp patent-search "3GPP RedCap reduced capability UE background" --limit 3
python -m agent3gpp patent-background "https://patents.google.com/patent/..."
```

专利背景只能用于反推 feature 的工程/商业痛点，不能作为 3GPP 标准结论。报告中应放入 `Patent Background / 专利背景与痛点反推` 章节，并标注为 `auxiliary_background` 或 `inference`。

## 深度研究输出

Agent 使用 `templates/deep-research-report.md` 作为报告结构约束。报告至少包含：

- Executive Summary / 结论摘要，逐条标注 `confirmed` / `evidence-grounded` / `needs_verification`
- Research Scope / 研究范围
- Methodology / 研究方法
- Source Inventory / 资料清单
- Evidence Table / 证据表
- Comparative Matrix / 对比矩阵
- Procedure Deep Dive / 流程深化
- Interpretation / 解释与影响
- Gaps, Risks, and Next Actions / 缺口、风险与下一步
- Reusable Brief / 可复用摘要

`confirmed` 结论必须有官方 URL 和 pointer。缺少 CR、TDoc、Meeting Report 或 clause pointer 的内容必须标为 `needs_verification` 或说明证据缺口。

## 当前能力

- 从 3GPP 官方 archive 下载 TS/TR ZIP
- 解压 ZIP
- 解析 DOCX / TXT / MD / CSV / HTML
- DOCX 解析默认保留 Word Track Changes：`+` 表示新增，`-` 表示删除，避免把删除内容当作当前有效条文
- 可选解析 PDF
- 生成 `data/index/metadata.csv`
- 建立 `data/index/research.db` SQLite FTS 检索库
- 建立基础关系表
- 使用 NVIDIA NIM chat completions 进行规划和报告生成
- 默认使用 `deepseek-ai/deepseek-v4-flash`
- 默认保存研究报告到 `runs/`
- 可查询 Google Patents 并提取 Background 作为辅助痛点分析

## 当前边界

- CR / TDoc / Meeting Report 的自动定位还没有做到完整 Portal 级覆盖。
- GraphRAG 目前是基础关系表，不是完整图数据库。
- 与 `3gpp-research-kit` 的复用关系还没有完全 SDK 化；当前仍使用内置 `agent3gpp/store.py` 跑通端到端闭环。
- `confirmed` 依赖本地检索到的官方资料、URL 和 pointer；关键结论仍建议专家复核。
- NVIDIA 模型目录会变化，可通过 `NVIDIA_MODEL`、`NVIDIA_PLANNER_MODEL`、`NVIDIA_WRITER_MODEL` 或 `--model` 调整。

## GitHub 发布前检查

- 不提交 `.env`
- 不提交 `data/incoming/`、`data/processed/`、`data/index/` 里的大文件和生成库
- 保留 `runs/.gitkeep`，不提交实际研究报告
- 运行 `python -m py_compile agent3gpp\store.py agent3gpp\nvidia_client.py agent3gpp\agent.py agent3gpp\__main__.py`

## Sources

- NVIDIA NIM for LLMs documents an OpenAI-compatible inference API with `POST /v1/chat/completions`.
- 当前 NVIDIA `/v1/models` 返回的可用模型包括 `qwen/qwen3.5-397b-a17b`、`qwen/qwen3.5-122b-a10b`、`qwen/qwen3-coder-480b-a35b-instruct`、`deepseek-ai/deepseek-v4-pro`、`deepseek-ai/deepseek-v4-flash`、`minimaxai/minimax-m2.7`。本项目默认选择实测更稳定的 `deepseek-ai/deepseek-v4-flash` 作为报告 Writer。
