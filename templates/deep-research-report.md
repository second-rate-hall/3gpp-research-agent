# <研究主题> 深度研究报告

## 1. Executive Summary / 结论摘要

- 用 5-8 条结论回答问题。
- 每条结论必须标注 `confirmed` / `evidence-grounded` / `inference` / `needs_verification`。
- 不允许把解释性判断写成标准事实。

## 2. Research Scope / 研究范围

- 解释用户问题的边界。
- 列出纳入的 RAT、规范、release 或 procedure。
- 列出明确排除的范围。
- 说明当前资料为什么足够或为什么不足。

## 3. Methodology / 研究方法

- 说明 Planner 生成的研究计划。
- 说明下载、解析、索引、检索和验证流程。
- 说明 DOCX 是否经过 Track Changes 感知解析。
- 说明是否使用 patent background 作为辅助痛点分析。
- 定义什么情况下可以标为 confirmed。

## 4. Source Inventory / 资料清单

| source_id | spec_id | title | official_url | parser | parse_status | role_in_report |
| --- | --- | --- | --- | --- | --- | --- |

## 5. Evidence Table / 证据表

| id | claim | source_type | source_id | spec_id | official_url | pointer | exact_evidence_or_snippet | status | confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 6. Patent Background / 专利背景与痛点反推

只在问题涉及 feature 背后的商业、实现或工程痛点时使用。

| feature / topic | patent source | assignee / inventor | background excerpt | inferred pain point | linked 3GPP evidence | status |
| --- | --- | --- | --- | --- | --- | --- |

规则：

- 专利背景只能标注为 `auxiliary_background` 或 `inference`。
- 专利背景不能单独支撑 3GPP 标准结论。
- 必须区分“专利文本描述的背景问题”和“3GPP 官方确认的设计动机”。
- 如果没有 CR/TDoc/Meeting Report 支撑，不能把专利背景写成 3GPP 官方动机。

## 7. Comparative Matrix / 对比矩阵

比较 4G/5G、release、规范或流程时必须使用本节。

| axis | A evidence | B evidence | similarity | difference | status |
| --- | --- | --- | --- | --- | --- |

## 8. Procedure Deep Dive / 流程深化

- Trigger / preconditions
- Messages
- State transitions
- Context and security handling
- Failure and fallback behavior
- Implementation impact

## 9. Interpretation / 解释与影响

- 用证据解释技术含义。
- 明确区分标准事实、证据支持的推断、待核验判断。
- 对实现、测试、互操作和问题定位给出影响分析。
- 如果引用了专利背景，只能作为痛点解释或研发动机线索。

## 10. Gaps, Risks, and Next Actions / 缺口、风险与下一步

- 缺失的 CR、TDoc、Meeting Report 或 clause pointer。
- 尚未能从官方资料确认的结论。
- 需要继续查询的 patent background、CR/TDoc 或会议材料。
- 下一步应调用的工具、下载范围或验证动作。

## 11. Reusable Brief / 可复用摘要

写成一段工程笔记，可直接放入设计说明、问题定位记录或标准学习笔记。
