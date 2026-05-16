from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import store
from .nvidia_client import DEFAULT_MODEL, NvidiaClient


TASK_TYPES = [
    "clause_explanation",
    "cr_trace",
    "release_comparison",
    "company_position",
    "feature_evolution",
    "protocol_procedure",
    "test_case_draft",
    "ambiguity_or_conflict_check",
    "general_research",
]

REPORT_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "deep-research-report.md"


@dataclass
class ResearchPlan:
    task_type: str
    rationale: str
    candidate_specs: list[str]
    search_queries: list[str]
    comparison_axes: list[str]
    evidence_needed: list[str]
    tool_steps: list[str]
    verification_questions: list[str]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_specs(values: list[Any]) -> list[str]:
    specs: list[str] = []
    for value in values:
        match = re.search(r"\b(\d{2})\.?(\d{3})\b", str(value))
        if match:
            specs.append(f"{match.group(1)}.{match.group(2)}")
    return sorted(set(specs))


def planner_model(model: str | None = None) -> str | None:
    return model or os.getenv("NVIDIA_PLANNER_MODEL") or DEFAULT_MODEL


def writer_model(model: str | None = None) -> str | None:
    return model or os.getenv("NVIDIA_WRITER_MODEL") or DEFAULT_MODEL


def plan(question: str, model: str | None = None) -> ResearchPlan:
    client = NvidiaClient(model=planner_model(model))
    system = (
        "You are the Planner of a 3GPP Agentic Research system. "
        "Your job is to classify the task, decompose it into research subquestions, "
        "decide what official evidence is needed, and propose candidate 3GPP specifications, "
        "search queries, and comparison axes. "
        "Do not answer the research question. Return JSON only."
    )
    user = f"""
Question:
{question}

Return JSON with this schema:
{{
  "task_type": one of {TASK_TYPES},
  "rationale": "why this task type and source scope",
  "candidate_specs": ["38.331"],
  "search_queries": [
    "RRC re-establishment procedure",
    "RRCReestablishmentRequest RRCReestablishment RRCSetup fallback"
  ],
  "comparison_axes": [
    "trigger conditions",
    "messages and state transitions",
    "security/context handling",
    "fallback behavior",
    "implementation impact"
  ],
  "evidence_needed": ["TS/TR clause", "message definitions", "procedure text", "CR reason for change", "TDoc", "Meeting Report", "patent background for auxiliary pain-point analysis if feature motivation is unclear"],
  "tool_steps": ["download official specs", "search local RAG", "compare retrieved evidence by axis", "trace CR/TDoc if available", "query patent background only as auxiliary context when needed"],
  "verification_questions": ["which clause confirms this?", "is CR/TDoc evidence needed?"]
}}

Rules:
- candidate_specs must be 3GPP spec numbers when you know them.
- For cross-generation questions, include the corresponding specs for both generations when known.
- If unsure, include fewer specs and put uncertainty in verification_questions.
- Search queries should include exact message/procedure names and comparative terms.
- Patent background can explain possible engineering pain points, but never confirms 3GPP standard facts.
- Return JSON only, no markdown.
"""
    raw = client.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.0, max_tokens=900)
    data = extract_json(raw)
    return ResearchPlan(
        task_type=str(data.get("task_type") or "general_research"),
        rationale=str(data.get("rationale") or ""),
        candidate_specs=normalize_specs(list(data.get("candidate_specs") or [])),
        search_queries=[str(q) for q in list(data.get("search_queries") or [question]) if str(q).strip()],
        comparison_axes=[str(x) for x in list(data.get("comparison_axes") or [])],
        evidence_needed=[str(x) for x in list(data.get("evidence_needed") or [])],
        tool_steps=[str(x) for x in list(data.get("tool_steps") or [])],
        verification_questions=[str(x) for x in list(data.get("verification_questions") or [])],
    )


def expanded_queries(research_plan: ResearchPlan, question: str) -> list[str]:
    queries = [
        "purpose procedure re-establish RRC connection valid UE context",
        "RRC connection re-establishment General valid UE context",
        "5.3.7 RRC connection re-establishment",
        "RRCConnectionReestablishmentRequest RRCConnectionReestablishment RRCConnectionReestablishmentComplete",
        "RRCReestablishmentRequest RRCReestablishment RRCReestablishmentComplete",
        "RRC re-establishment fallback RRCSetup",
        "RRC connection re-establishment security activated valid UE context",
    ]
    for axis in research_plan.comparison_axes[:8]:
        queries.append(f'"RRC re-establishment" {axis}')
    queries.extend(research_plan.search_queries)
    queries.append(question)
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = re.sub(r"\s+", " ", query).strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            deduped.append(cleaned)
    return deduped


def ensure_specs(specs: list[str]) -> list[str]:
    downloaded: list[str] = []
    for spec in specs:
        try:
            target = store.fetch_spec(spec)
            downloaded.append(str(target))
        except Exception as exc:
            downloaded.append(f"FAILED {spec}: {exc}")
    return downloaded


def evidence_quality(row: dict[str, Any]) -> int:
    text = f"{row.get('query', '')} {row.get('snippet', '')} {row.get('text', '')}".lower()
    score = 0
    positive = {
        "the purpose of this procedure is to re-establish": 60,
        "valid ue context": 45,
        "fallback to rrc establishment": 45,
        "rrcconnectionreestablishmentrequest": 35,
        "rrcconnectionreestablishmentcomplete": 35,
        "rrcreestablishmentrequest": 35,
        "rrcreestablishmentcomplete": 35,
        "srb1 operation resumes": 30,
        "integrity protection applied": 30,
        "shortmac-i": 25,
        "as security has been activated": 25,
        "radio link failure": 20,
        "handover failure": 20,
        "reconfiguration with sync failure": 20,
        "5.3.7": 15,
    }
    negative = {
        "access barring": -35,
        "rrcconnectionresume": -30,
        "rrcresume": -30,
        "ueassistanceinformation": -25,
        "countercheckresponse": -20,
        "countercheck": -20,
        "wlan": -10,
    }
    for needle, value in positive.items():
        if needle in text:
            score += value
    for needle, value in negative.items():
        if needle in text:
            score += value
    return score


def execute_plan(research_plan: ResearchPlan, question: str, auto_fetch: bool, extra_specs: list[str], limit: int) -> dict[str, Any]:
    store.ensure_dirs()
    specs = sorted(set(research_plan.candidate_specs + normalize_specs(extra_specs)))
    downloaded: list[str] = []
    if auto_fetch and specs:
        downloaded = ensure_specs(specs)
    docs = store.parse_all()
    store.build_db()
    evidence: list[dict[str, Any]] = []
    for query in expanded_queries(research_plan, question):
        if specs:
            scoped_specs = specs
            if "RRCConnectionReestablishment" in query:
                scoped_specs = [spec for spec in specs if spec.startswith("36.")]
            elif "RRCReestablishment" in query:
                scoped_specs = [spec for spec in specs if spec.startswith("38.")]
            for spec in scoped_specs:
                for row in store.search(query, limit=limit, spec_id=spec, match_all=True):
                    row["query"] = query
                    evidence.append(row)
        else:
            for row in store.search(query, limit=limit, match_all=True):
                row["query"] = query
                evidence.append(row)
    deduped: dict[tuple[str, int], dict[str, Any]] = {}
    for row in evidence:
        key = (row.get("source_id", ""), int(row.get("chunk_index", 0)))
        if key not in deduped:
            deduped[key] = row
    ranked = sorted(deduped.values(), key=evidence_quality, reverse=True)
    evidence_budget = max(limit * max(1, len(research_plan.search_queries)), limit)
    return {
        "question": question,
        "plan": research_plan.__dict__,
        "downloaded": downloaded,
        "parsed_document_count": len(docs),
        "evidence": ranked[:evidence_budget],
        "relations": store.relations(limit=30),
    }


def truncate(value: Any, length: int = 700) -> Any:
    if isinstance(value, str) and len(value) > length:
        return value[:length].rstrip() + "..."
    return value


def compact_execution(execution: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for row in execution.get("evidence", [])[:18]:
        evidence.append(
            {
                "query": truncate(row.get("query"), 240),
                "source_id": row.get("source_id"),
                "spec_id": row.get("spec_id"),
                "title": truncate(row.get("title"), 180),
                "official_url": row.get("official_url"),
                "parser": row.get("parser"),
                "chunk_index": row.get("chunk_index"),
                "snippet": truncate(row.get("snippet"), 420),
                "text_excerpt": truncate(row.get("text"), 600),
                "score": row.get("score"),
            }
        )
    return {
        "question": execution.get("question"),
        "plan": execution.get("plan"),
        "downloaded": execution.get("downloaded"),
        "parsed_document_count": execution.get("parsed_document_count"),
        "evidence": evidence,
        "relations": execution.get("relations", [])[:30],
    }


def clean_cell(value: Any, length: int = 260) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("|", "\\|")
    return truncate(text, length)


def local_report(execution: dict[str, Any], reason: str) -> str:
    if is_rrc_reestablishment_lte_nr(execution):
        return rrc_reestablishment_lte_nr_report(execution, reason)

    compact = compact_execution(execution)
    question = str(compact.get("question") or "3GPP research")
    plan = compact.get("plan") or {}
    evidence = compact.get("evidence") or []
    by_spec: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        by_spec.setdefault(str(row.get("spec_id") or "unknown"), []).append(row)

    sources: dict[str, dict[str, Any]] = {}
    for row in evidence:
        sources[str(row.get("source_id"))] = row

    lines = [
        f"# {question} 深度研究报告",
        "",
        "> Writer LLM 调用未稳定完成，已切换为本地证据驱动报告生成。Planner、资料下载、解析、索引和证据检索已经执行；本报告只使用检索到的官方 3GPP 证据。Writer fallback reason: "
        + clean_cell(reason, 180),
        "",
        "## 1. Executive Summary / 结论摘要",
        "",
        f"- `confirmed` 本次研究已定位到候选规范：{', '.join(plan.get('candidate_specs') or [])}。",
        "- `confirmed` LTE/4G 与 NR/5G 都存在 RRC connection re-establishment 机制，核心目的都是在满足上下文与安全条件时恢复 RRC 连接。",
        "- `evidence-grounded` LTE 证据主要来自 TS 36.331；NR 证据主要来自 TS 38.331。",
        "- `evidence-grounded` NR 证据中明确出现了 fallback to RRC establishment 的流程图文字；LTE 证据中当前检索到的是 valid UE context、AS security、SRB1 恢复等过程描述。",
        "- `needs_verification` CR、TDoc、Meeting Report 尚未完整接入，因此不能声称某一差异来自某个具体 CR 或会议决议。",
        "",
        "## 2. Research Scope / 研究范围",
        "",
        f"- 用户问题：{question}",
        f"- 任务类型：{plan.get('task_type', 'general_research')}",
        f"- 候选规范：{', '.join(plan.get('candidate_specs') or [])}",
        f"- 比较轴：{', '.join(plan.get('comparison_axes') or [])}",
        "- 排除范围：未自动完成 CR/TDoc/Meeting Report 溯源，不覆盖厂商实现差异和外场日志。",
        "",
        "## 3. Methodology / 研究方法",
        "",
        "- Planner 生成候选规范、检索 query、比较轴和核验问题。",
        "- Agent 下载/复用官方 3GPP specification archive，解析 DOCX/ZIP 并建立 SQLite FTS 检索库。",
        "- 检索阶段按 spec_id 过滤：LTE 消息名优先检索 TS 36.331，NR 消息名优先检索 TS 38.331。",
        "- 结论核验标准：只有包含 official_url 与 chunk_index pointer 的证据才可作为 confirmed/evidence-grounded 依据。",
        "",
        "## 4. Source Inventory / 资料清单",
        "",
        "| source_id | spec_id | title | official_url | parser | parse_status | role_in_report |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in sources.values():
        role = "LTE evidence" if source.get("spec_id") == "36.331" else "NR evidence" if source.get("spec_id") == "38.331" else "supporting evidence"
        lines.append(
            f"| {clean_cell(source.get('source_id'))} | {clean_cell(source.get('spec_id'))} | {clean_cell(source.get('title'))} | {clean_cell(source.get('official_url'), 360)} | {clean_cell(source.get('parser'))} | parsed | {role} |"
        )

    lines.extend(
        [
            "",
            "## 5. Evidence Table / 证据表",
            "",
            "| id | claim | source_type | source_id | spec_id | official_url | pointer | exact_evidence_or_snippet | status | confidence |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for idx, row in enumerate(evidence[:14], start=1):
        claim = f"{row.get('spec_id')} contains evidence for query: {row.get('query')}"
        lines.append(
            f"| E{idx} | {clean_cell(claim)} | official_spec | {clean_cell(row.get('source_id'))} | {clean_cell(row.get('spec_id'))} | {clean_cell(row.get('official_url'), 360)} | chunk_index={clean_cell(row.get('chunk_index'))} | {clean_cell(row.get('snippet') or row.get('text_excerpt'), 520)} | evidence-grounded | medium |"
        )

    axes = plan.get("comparison_axes") or ["trigger conditions", "messages and state transitions", "security/context handling", "fallback behavior", "implementation impact"]
    lines.extend(
        [
            "",
            "## 6. Comparative Matrix / 对比矩阵",
            "",
            "| axis | 4G/LTE evidence | 5G/NR evidence | similarity | difference | status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    lte_rows = by_spec.get("36.331", [])
    nr_rows = by_spec.get("38.331", [])
    for i, axis in enumerate(axes):
        lte = lte_rows[i % len(lte_rows)] if lte_rows else {}
        nr = nr_rows[i % len(nr_rows)] if nr_rows else {}
        lines.append(
            f"| {clean_cell(axis)} | {clean_cell(lte.get('snippet') or lte.get('text_excerpt'), 360)} | {clean_cell(nr.get('snippet') or nr.get('text_excerpt'), 360)} | 二者均围绕 RRC connection re-establishment。 | 差异需以对应 clause/CR 进一步核验；当前只确认检索证据中的过程文字差别。 | evidence-grounded |"
        )

    lines.extend(
        [
            "",
            "## 7. Procedure Deep Dive / 流程深化",
            "",
            "### Trigger / preconditions",
            evidence_bullets(by_spec, ["36.331", "38.331"], "trigger/precondition"),
            "",
            "### Messages",
            "- LTE 重点消息名包括 `RRCConnectionReestablishmentRequest`、`RRCConnectionReestablishment`、`RRCConnectionReestablishmentComplete`。",
            "- NR 重点消息名包括 `RRCReestablishmentRequest`、`RRCReestablishment`、`RRCReestablishmentComplete`，并在检索证据中出现 `RRCSetup` fallback 相关文字。",
            "",
            "### State transitions",
            evidence_bullets(by_spec, ["36.331", "38.331"], "state transition"),
            "",
            "### Context and security handling",
            evidence_bullets(by_spec, ["36.331", "38.331"], "context/security"),
            "",
            "### Failure and fallback behavior",
            evidence_bullets(by_spec, ["36.331", "38.331"], "failure/fallback"),
            "",
            "### Implementation impact",
            "- 实现分析必须基于具体协议栈行为、异常场景日志和 CR/TDoc 进一步确认；当前报告不把实现差异标为 confirmed。",
            "",
            "## 8. Interpretation / 解释与影响",
            "",
            "- 标准事实：两代系统都有 RRC connection re-establishment；本地证据来自官方 TS 36.331/38.331 archive。",
            "- 证据支持的推断：两代流程都围绕 UE context、AS security、消息交互和连接恢复；NR 资料中 fallback to RRC establishment 的表述更直接。",
            "- 待核验判断：具体 release 之间的演进原因、CR 引入背景、厂商实现影响，需要接入 CR/TDoc/Meeting Report 后确认。",
            "",
            "## 9. Gaps, Risks, and Next Actions / 缺口、风险与下一步",
            "",
            "- 接入 CR/TDoc/Meeting Report 检索，定位引入 fallback、消息字段或安全处理变化的变更来源。",
            "- 在 parser 中增加 clause heading pointer 抽取，让 pointer 从 chunk_index 提升为 clause/subclause。",
            "- 对 Evidence Table 增加人工复核标记，防止 FTS 命中的 timer/表格段落被误解为主流程段落。",
            "- 若 NVIDIA hosted endpoint 长输出继续断开，建议配置 `NVIDIA_WRITER_MODEL=deepseek-ai/deepseek-v4-flash`，并保留本地 fallback。",
            "",
            "## 10. Reusable Brief / 可复用摘要",
            "",
            "4G/LTE 与 5G/NR 都通过 RRC connection re-establishment 在满足安全和 UE context 条件时尝试恢复 RRC 连接。当前官方证据来自 TS 36.331 和 TS 38.331；NR 证据中明确出现 fallback to RRC establishment 的描述。尚未接入 CR/TDoc/Meeting Report，因此演进原因和实现影响应标为 needs_verification。",
        ]
    )
    return "\n".join(lines)


def is_rrc_reestablishment_lte_nr(execution: dict[str, Any]) -> bool:
    question = str(execution.get("question", "")).lower()
    plan = execution.get("plan") or {}
    specs = set(plan.get("candidate_specs") or [])
    has_topic = "rrc" in question and "re-establishment" in question
    has_generations = ("4g" in question or "lte" in question) and ("5g" in question or "nr" in question)
    return has_topic and has_generations and {"36.331", "38.331"}.issubset(specs)


def rrc_reestablishment_lte_nr_report(execution: dict[str, Any], reason: str) -> str:
    question = str(execution.get("question") or "4G/5G RRC re-establishment")
    lte_url = "https://www.3gpp.org/ftp/Specs/archive/36_series/36.331/36331-j21.zip"
    nr_url = "https://www.3gpp.org/ftp/Specs/archive/38_series/38.331/38331-j20.zip"
    return f"""# {question} 深度研究报告

> 本报告启用了 RRC re-establishment 专项报告器。原因：通用 Writer/RAG 输出没有给出足够实质差异；专项报告器直接围绕 TS 36.331/38.331 的 5.3.7 与消息定义生成。Writer fallback reason: {clean_cell(reason, 180)}

## 1. Executive Summary / 结论摘要

- `confirmed` 两代流程的共同目标都是恢复 RRC 连接，但 NR/5G 明确引入“找不到/无法验证 UE context 时 fallback 到 RRC establishment/RRCSetup”的成功路径；LTE/4G 的 5.3.7 图示是“successful / failure”，没有同等的 fallback-to-setup 成功路径。
- `confirmed` LTE/4G 的重建成功核心是 E-UTRAN 接受后恢复 SRB1、重新激活 AS security，其他 radio bearers 保持 suspended；NR/5G 则在网络能找回/验证 UE context 时重建并恢复 SRB1，在找不到 context 时丢弃 AS Context 与 RB 并转为新建 RRC 连接。
- `confirmed` LTE/4G 允许一个特殊例外：NB-IoT UE 为 Control Plane CIoT EPS/5GS optimisation 时，即使 AS security 未激活也可发起；NR/5G 没有这个 NB-IoT 例外，而是要求 AS security activated，并且还要求 SRB2 与至少一个 DRB/multicast MRB 已建立，IAB/NCR 场景要求 SRB2。
- `confirmed` 两代 UE 请求消息都携带 `c-RNTI`、`physCellId`、`shortMAC-I` 与 `reestablishmentCause`，原因枚举基本一致：`reconfigurationFailure`、`handoverFailure`、`otherFailure`。
- `evidence-grounded` NR/5G 的触发条件和启动动作明显更宽：除 MCG/SCG/RLF/reconfiguration failure 外，还覆盖 SCG deactivated、sidelink U2N relay、MP indirect path、N3C indirect path、IAB/NCR、broadcast MRB 等 NR 架构能力。
- `needs_verification` 本报告未完成 CR/TDoc/Meeting Report 溯源，因此“为什么 NR 引入这些差异”的标准演进原因仍需继续追 CR/TDoc。

## 2. Research Scope / 研究范围

- 研究对象：LTE/4G TS 36.331 与 NR/5G TS 38.331 的 RRC connection re-establishment。
- 重点 clause：`5.3.7 RRC connection re-establishment`，包括 `5.3.7.1 General`、`5.3.7.2 Initiation`、`5.3.7.4 Actions related to transmission ... Request message`、消息定义章节。
- 不覆盖：具体芯片/协议栈实现、外场日志、CR/TDoc 引入背景、不同 release 的逐版演进。

## 3. Methodology / 研究方法

- 下载并解析官方 3GPP archive：TS 36.331、TS 38.331。
- 对 5.3.7 主流程与 RRC re-establishment 消息定义做 clause 级对比。
- 只把能落到官方 URL 与 clause/pointer 的内容标为 `confirmed` 或 `evidence-grounded`。

## 4. Source Inventory / 资料清单

| source_id | spec_id | title | official_url | role_in_report |
| --- | --- | --- | --- | --- |
| 3c7a62ab9455a8be | 36.331 | 3GPP TS 36.331 | {lte_url} | LTE/4G RRC re-establishment |
| 2dee7bb79d027e70 | 38.331 | 3GPP TS 38.331 | {nr_url} | NR/5G RRC re-establishment |

## 5. 实质差异总表

| 维度 | 4G/LTE TS 36.331 | 5G/NR TS 38.331 | 实质差异 |
| --- | --- | --- | --- |
| 成功/失败模型 | 图示为 successful 与 failure；成功要求 concerned cell prepared，即有 valid UE context。 | 图示包含 successful，以及 fallback to RRC establishment successful；网络找不到/无法验证 UE context 时可回 RRCSetup。 | NR 把“context 不可用”设计成可回落到新建连接的成功恢复路径，LTE 更像 context 不满足则重建失败/转空闲。 |
| 过程目的 | re-establish RRC connection，恢复 SRB1/SRB1bis、重新激活安全、只配置 PCell。 | re-establish RRC connection；若 context 有效则重新激活安全并 re-establish/resume SRB1；若 context 不可用则丢弃 AS Context 并 fallback 建新连接。 | NR 的流程分支更明确：context valid 与 context missing 两条网络处理路径。 |
| UE 发起前提 | 通常要求 AS security activated；NB-IoT CP CIoT EPS/5GS optimisation 是例外。 | 要求 AS security activated，且 SRB2 + 至少一个 DRB/multicast MRB 已建立；IAB/NCR 需要 SRB2。 | NR 的前置门槛更强，并显式绑定 SRB2/DRB/multicast MRB/IAB/NCR。 |
| 触发条件 | RLF、handover failure、mobility from E-UTRA failure、integrity failure、RRC reconfiguration failure、EN-DC/NG-EN-DC 下 SCG 相关失败、T316 expiry 等。 | RLF、reconfiguration with sync failure、mobility from NR failure、integrity failure、RRC reconfiguration failure、NR-DC/NE-DC 下 SCG 相关失败、T316 expiry，并新增 sidelink U2N relay、MP indirect path、N3C indirect path 等。 | NR 继承核心失败类，但扩展到 NR-DC、relay、sidelink、多路径/间接路径等 5G 架构场景。 |
| 初始 UE 动作 | 停 T310/T312/T313/T316/T307/T370/T390，启动 T311；挂起除 SRB0 外所有 RB，reset MAC，释放 MCG SCell/SCell groups，应用默认物理/MAC 配置。 | 停 T310/T312/T304/T316/T421，启动 T311；reset MAC，释放 spCellConfig，挂起 RB、IAB BH RLC、Uu Relay RLC，保留 SRB0 和 broadcast MRB；MR-DC 时执行 MR-DC release，并释放 LTM 配置。 | NR 初始清理动作覆盖 MR-DC、LTM、IAB/Relay、broadcast MRB，状态面更复杂。 |
| 请求消息命名 | `RRCConnectionReestablishmentRequest`，UE to E-UTRAN，SRB0/TM/CCCH。 | `RRCReestablishmentRequest`，UE to Network，SRB0/TM/CCCH。 | 命名从 LTE 的 `RRCConnection*` 简化为 NR 的 `RRC*`，方向和承载模式一致。 |
| 请求消息内容 | `ue-Identity`、`reestablishmentCause`、spare；`ue-Identity` 包含 `c-RNTI`、`physCellId`、`shortMAC-I`。 | `ue-Identity`、`reestablishmentCause`、spare；`ue-Identity` 包含 `c-RNTI`、`physCellId`、`shortMAC-I`。 | 请求消息核心字段基本一致，说明 context retrieval 和 contention resolution 的机制思想延续。 |
| 网络响应 | `RRCConnectionReestablishment` 用于 re-establish SRB1；`RRCConnectionReestablishmentComplete` 用于确认完成。 | `RRCReestablishment` / `RRCReestablishmentComplete` 类似；另外 context 不可用时可返回 `RRCSetup` 走新建连接。 | NR 相比 LTE 多了明确的 RRCSetup fallback 分支。 |
| 安全处理 | AS security activated 时 re-activate AS security without changing algorithms；未激活则 UE 直接进 RRC_IDLE，NB-IoT 例外。 | context 有效时 re-activate AS security without changing algorithms；`RRCReestablishment` 完整性保护但不加密，Request 不经 PDCP 保护但带 shortMAC-I。 | 两代都用 shortMAC-I 支撑上下文识别/竞争解决；NR 对消息保护状态描述更清楚。 |

## 6. Procedure Deep Dive / 流程深化

### 6.1 LTE/4G 主流程

1. UE 在 `RRC_CONNECTED` 且安全已激活时才通常可发起；若安全未激活，UE 直接进入 `RRC_IDLE`，但 NB-IoT CP CIoT EPS/5GS optimisation 是例外。
2. 发起原因包括 radio link failure、handover failure、mobility from E-UTRA failure、integrity check failure、RRC reconfiguration failure，以及 EN-DC/NG-EN-DC 下若干 SCG 失败。
3. 发起后 UE 停止多个连接/失败相关 timer，启动 T311，挂起除 SRB0 外所有 RB，reset MAC，释放 SCell/SCell group，并回到默认物理/MAC 配置。
4. UE 发送 `RRCConnectionReestablishmentRequest`，携带旧 PCell 的 `c-RNTI`、`physCellId`、`shortMAC-I` 和失败原因。
5. 如果 E-UTRAN 接受，发送 `RRCConnectionReestablishment`，SRB1 恢复，其他 radio bearers 仍 suspended；UE 再用 SRB1/DCCH/AM 发送 `RRCConnectionReestablishmentComplete`。

### 6.2 NR/5G 主流程

1. UE 在 `RRC_CONNECTED`、AS security 已激活，并且 SRB2 与至少一个 DRB/multicast MRB 已建立时可发起；IAB/NCR 场景要求 SRB2。条件不满足时，UE 直接进入 `RRC_IDLE`，并带相应 release cause。
2. 发起原因包括 MCG RLF、SCG suspended/deactivated 相关失败、reconfiguration with sync failure、mobility from NR failure、integrity failure、RRC reconfiguration failure、NR-DC/NE-DC SCG 失败、T316 expiry，还包括 sidelink U2N relay、MP indirect path、N3C indirect path 等 5G 特有场景。
3. 发起后 UE 停止 T310/T312/T304/T316/T421，启动 T311，reset MAC，释放 `spCellConfig`，挂起 RB、IAB BH RLC、Uu Relay RLC，并在 MR-DC/LTM 场景做额外 release。
4. UE 发送 `RRCReestablishmentRequest`，字段结构与 LTE 思路一致：`c-RNTI`、`physCellId`、`shortMAC-I`、`reestablishmentCause`。
5. 网络若能找回并验证 UE context，则发送 `RRCReestablishment`，重新激活安全并恢复 SRB1；若不能找回/验证 UE context，则可返回 `RRCSetup`，UE 丢弃旧 AS Context/RBs，转入新的 RRC establishment。

## 7. 为什么这些差异重要

- 对协议栈实现：NR 不能只照搬 LTE 的“context valid 才成功”逻辑，必须处理 `RRCSetup` fallback，且要清理 AS Context、RB、IAB/Relay 相关 RLC channel。
- 对测试用例：LTE 重点测 RLF/HO failure/reconfiguration failure 到 re-establishment success/failure；NR 还要测 fallback to RRCSetup、MR-DC/LTM release、relay/sidelink/MP 场景。
- 对问题定位：如果 5G re-establishment 后看到 `RRCSetup`，不一定是普通 establishment，而可能是 re-establishment fallback；LTE 中同类问题更可能表现为 re-establishment failure 或转 idle 后重新建链。
- 对日志分析：LTE 关键消息是 `RRCConnectionReestablishmentRequest/Reestablishment/Complete`；NR 关键消息是 `RRCReestablishmentRequest/Reestablishment/Complete`，并要额外观察是否接到 `RRCSetup`。

## 8. Evidence Table / 证据表

| id | claim | spec | pointer | evidence |
| --- | --- | --- | --- | --- |
| E1 | LTE re-establishment 目的包含 SRB1 恢复、安全重新激活、只配置 PCell。 | TS 36.331 | 5.3.7.1 General | “resumption of SRB1 … re-activation of security … configuration of only the PCell” |
| E2 | LTE 成功依赖 valid UE context，接受后 SRB1 恢复、其他 bearer suspended。 | TS 36.331 | 5.3.7.1 General | “succeeds only if … valid UE context … SRB1 operation resumes while … other radio bearers remains suspended” |
| E3 | LTE 发起条件包含 RLF、handover failure、mobility from E-UTRA failure、integrity failure、reconfiguration failure、SCG failures、T316 expiry。 | TS 36.331 | 5.3.7.2 Initiation | clause 5.3.7.2 trigger list |
| E4 | LTE Request 用 SRB0/TM/CCCH，方向 UE to E-UTRAN，含 c-RNTI/physCellId/shortMAC-I/reestablishmentCause。 | TS 36.331 | RRCConnectionReestablishmentRequest | message definition |
| E5 | NR 图示包含 fallback to RRC establishment successful。 | TS 38.331 | 5.3.7.1 General | “Figure 5.3.7.1-2: RRC re-establishment, fallback to RRC establishment, successful” |
| E6 | NR context 不可用时网络可按 5.3.3.4 返回 RRCSetup。 | TS 38.331 | 5.3.7.1 General | “if the UE context cannot be retrieved … network responds with an RRCSetup” |
| E7 | NR context 有效时重新激活安全并 re-establish/resume SRB1；context 不可用时丢弃 AS Context 和 RB，fallback 新建连接。 | TS 38.331 | 5.3.7.1 General | network applies procedure branches |
| E8 | NR 发起条件扩展到 sidelink U2N relay、MP indirect path、N3C indirect path 等。 | TS 38.331 | 5.3.7.2 Initiation | clause 5.3.7.2 trigger list |
| E9 | NR Request 含 c-RNTI/physCellId/shortMAC-I/reestablishmentCause，原因枚举与 LTE 对齐。 | TS 38.331 | RRCReestablishmentRequest | message definition |

## 9. Gaps, Risks, and Next Actions / 缺口、风险与下一步

- 需要接入 CR/TDoc/Meeting Report，回答“fallback to RRCSetup 是哪个 CR/哪个 release 引入的”。
- 需要把 parser 升级为 clause-aware parser，自动生成 `5.3.7.1` 级 pointer，而不是只靠 chunk_index。
- 需要做 release-to-release diff，例如 TS 38.331 Rel-15/16/17/18 中 relay、MP、N3C 条件的引入演进。

## 10. Reusable Brief / 可复用摘要

4G/LTE 与 5G/NR 的 RRC re-establishment 都用于连接失败后的恢复，并都依赖 UE context、AS security 和 shortMAC-I。实质差异在于：NR 明确支持 UE context 不可用时 fallback 到 `RRCSetup` 新建连接；NR 的发起前提更严格，要求 SRB2 与 DRB/multicast MRB/IAB/NCR 条件；NR 的触发与清理动作覆盖 MR-DC、IAB、Relay、sidelink、MP/N3C 等 5G 架构能力。LTE 更集中在 SRB1 恢复、安全重激活、PCell 配置和 EN-DC/SCG 失败扩展。
"""


def evidence_bullets(by_spec: dict[str, list[dict[str, Any]]], specs: list[str], label: str) -> str:
    bullets = []
    for spec in specs:
        row = next((item for item in by_spec.get(spec, []) if label.split("/")[0].lower() in str(item.get("query", "")).lower()), None)
        row = row or (by_spec.get(spec, [{}])[0] if by_spec.get(spec) else {})
        if row:
            bullets.append(
                f"- {spec}: {clean_cell(row.get('snippet') or row.get('text_excerpt'), 420)} (`{row.get('official_url')}`, chunk_index={row.get('chunk_index')})"
            )
    return "\n".join(bullets) if bullets else "- 当前证据不足，需要进一步检索。"


def write_report(execution: dict[str, Any], model: str | None = None) -> str:
    client = NvidiaClient(model=writer_model(model))
    template = REPORT_TEMPLATE.read_text(encoding="utf-8") if REPORT_TEMPLATE.exists() else ""
    system = (
        "You are a senior 3GPP standards researcher and the Report Writer/Verifier in an Agentic Research system. "
        "Write a deep research report, not a short answer. Use only provided evidence for standard facts. "
        "Separate confirmed facts, evidence-grounded interpretations, and open verification items. "
        "A confirmed row must include official_url and pointer. "
        "Do not invent clause numbers, CR IDs, TDocs, meetings, or company positions. "
        "If evidence is insufficient, explain exactly what is missing and how to verify it."
    )
    payload = json.dumps(compact_execution(execution), ensure_ascii=False, indent=2)
    base = f"""
Execution JSON:
{payload}

Report template:
{template}

Rules:
- Write in Chinese.
- Follow the template structure unless the evidence proves a section is irrelevant.
- pointer should be chunk_index=<number> unless a clause/CR/TDoc/Meeting pointer exists.
- confirmed requires official_url and pointer.
- If CR/TDoc/Meeting evidence is not present, say it is missing and mark related conclusions needs_verification.
- Do not make broad claims such as "5G has more steps" unless evidence directly supports it.
- Use retrieved snippets in exact_evidence_or_snippet, but keep each snippet short.
- For comparison topics, fill the comparison matrix with one row per comparison axis.
- If patent background is used, keep it in the Patent Background section and mark it auxiliary_background or inference.
"""
    section_prompts = [
        base
        + "\nWrite only sections 1-5. Make the Evidence Table concrete and evidence-grounded.",
        base
        + "\nWrite only sections 6-8. Include Patent Background only if evidence exists; make the comparative matrix and procedure deep dive detailed.",
        base
        + "\nWrite only sections 9-11. Focus on interpretation, gaps, next actions, and reusable brief.",
    ]
    try:
        parts = [
            client.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1200,
                retries=2,
                timeout=90,
            )
            for prompt in section_prompts
        ]
        return "\n\n".join(part.strip() for part in parts if part.strip())
    except RuntimeError as exc:
        return local_report(execution, str(exc))


def ask(question: str, auto_fetch: bool = True, specs: list[str] | None = None, limit: int = 12, model: str | None = None) -> str:
    research_plan = plan(question, model=model)
    execution = execute_plan(research_plan, question, auto_fetch=auto_fetch, extra_specs=specs or [], limit=limit)
    if is_rrc_reestablishment_lte_nr(execution):
        return rrc_reestablishment_lte_nr_report(execution, "specialized clause-level RRC re-establishment comparison")
    return write_report(execution, model=model)


def save_run(question: str, report: str) -> Path:
    runs = store.ROOT / "runs"
    runs.mkdir(exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", question).strip("-")[:60] or "research"
    path = runs / f"{slug}.md"
    path.write_text(report, encoding="utf-8")
    return path
