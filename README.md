# 3GPP Research Agent

`3gpp-research-agent` is a local CLI agent for evidence-grounded 3GPP standards research.

Give it a research topic, and it can plan the investigation, download official 3GPP specification archives, parse documents, build a local SQLite FTS evidence database, retrieve evidence, and generate a structured research report with verification status.

It is designed for standards engineers, protocol researchers, and teams experimenting with agentic research over 3GPP material.

## What It Does

```text
research question
-> planner proposes task type, candidate specs, queries, comparison axes
-> fetch official 3GPP specs when needed
-> parse ZIP / DOCX / TXT / MD / CSV / HTML / optional PDF
-> build local evidence database
-> retrieve and rank evidence
-> call NVIDIA NIM compatible chat completions
-> write a deep research report under runs/
```

The agent is intentionally evidence-constrained. If CR, TDoc, Meeting Report, or clause-level evidence is missing, the report should mark the related conclusion as `needs_verification`.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Optional PDF parsing:

```bash
pip install -e ".[pdf]"
```

## Configure NVIDIA NIM

Do not commit real API keys.

```bash
copy .env.example .env
```

Edit `.env`:

```text
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=deepseek-ai/deepseek-v4-flash
```

Optional planner / writer split:

```text
NVIDIA_PLANNER_MODEL=qwen/qwen3.5-122b-a10b
NVIDIA_WRITER_MODEL=deepseek-ai/deepseek-v4-flash
```

## Quick Start

Run a full research task:

```bash
python -m agent3gpp "请分析4G和5G在RRC re-establishment流程的异同"
```

Equivalent explicit command:

```bash
python -m agent3gpp research "请分析4G和5G在RRC re-establishment流程的异同"
```

Print without saving:

```bash
python -m agent3gpp research "请分析4G和5G在RRC re-establishment流程的异同" --no-save
```

Inspect only the generated plan:

```bash
python -m agent3gpp plan "请分析4G和5G在RRC re-establishment流程的异同"
```

Manual evidence workflow:

```bash
python -m agent3gpp fetch-spec --spec 38.331
python -m agent3gpp parse
python -m agent3gpp search RRCReestablishment --limit 5
```

## Commands

| Command | Purpose |
| --- | --- |
| `research <question>` | Run full agentic research and save a report |
| `ask <question>` | Alias-style research command |
| `plan <question>` | Generate the research plan only |
| `fetch-spec --spec 38.331` | Download an official 3GPP spec archive |
| `parse` | Parse local source files and rebuild the index |
| `search <query>` | Search the local evidence database |
| `patent-search <query>` | Search Google Patents for auxiliary background |
| `patent-background <url>` | Extract patent background text from a patent URL |

Patent material is auxiliary only. It can help infer engineering or commercial pain points, but it cannot confirm 3GPP standards facts.

## Report Structure

Reports follow `templates/deep-research-report.md` and should include:

- Executive Summary with `confirmed` / `evidence-grounded` / `needs_verification` labels.
- Research Scope.
- Methodology.
- Source Inventory.
- Evidence Table.
- Comparative Matrix when relevant.
- Procedure Deep Dive.
- Interpretation and implementation impact.
- Gaps, risks, and next actions.
- Reusable engineering brief.

`confirmed` claims require an official URL and pointer. Missing CR, TDoc, Meeting Report, or clause evidence should be explicit.

## Local Data

The agent writes local working artifacts under:

```text
data/incoming/
data/processed/
data/index/
runs/
```

These are ignored by Git except for `.gitkeep` placeholders.

## Relationship To 3GPP Research Kit

`3gpp-research-kit` is the reusable workbench and evidence toolkit: workflows, templates, source notes, parsing/indexing/search commands, and evidence verification.

`3gpp-research-agent` is a dedicated CLI agent: planner, model orchestration, report writer, specialized report logic, and run management.

Current implementation note: this repository still contains a lightweight evidence store in `agent3gpp/store.py` so the agent can run independently. A future direction is to use `3gpp-research-kit` as the shared evidence backend and keep this repository focused on agent planning and report generation.

## Current Capabilities

- Official 3GPP spec archive download.
- ZIP extraction.
- DOCX / TXT / MD / CSV / HTML parsing.
- DOCX track-change aware parsing.
- Optional PDF parsing with `pypdf`.
- SQLite FTS evidence database.
- Basic relation table.
- NVIDIA NIM chat completions for planning and writing.
- Local fallback report generation for selected cases.
- Google Patents search/background extraction for auxiliary context.

## Current Limits

- CR / TDoc / Meeting Report automation is not portal-scale yet.
- GraphRAG is a basic relation table, not a full graph database.
- Clause pointers are often chunk-level unless more exact source metadata is available.
- Model availability on NVIDIA NIM can change; configure models through env vars or `--model`.
- Expert review is still required for high-impact standards conclusions.

## Safety

- Do not commit `.env`.
- Do not commit downloaded specs, generated indexes, or actual research reports.
- Treat third-party commentary, patents, and model outputs as leads, not official standards evidence.

## License

MIT.
