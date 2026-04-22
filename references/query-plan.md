# Query plan (4-phase) — schema, skip rules, examples

**Status: optional.** Default flow is to write the per-DB expression table
inline in the response. This file documents the structured plan format used
when ① you want a script-validatable artifact, or ② you opt into the gate via
`PAPER_SEARCH_GATE=1` (build_refs.py will then enforce
`scripts/expand_queries.py --plan plan.json` was run). The per-DB syntax table
below is also the syntax cheatsheet referenced from SKILL.md regardless.

## Phase summary

| # | Phase | Output key in plan |
|---|---|---|
| ① | 字段识别 — concept → field | `fields` |
| ② | 布尔归一化 — explicit AND/OR/NOT tree | `boolean` |
| ③ | 概念扩展 — synonym/bilingual/abbrev (skippable) | `expansion` |
| ④ | 按库构建 — per-database expression string | `per_db` |

Logical field codes: `topic` (default) · `TI` 题名 · `AB` 摘要 · `KW` 关键词 ·
`TKA` 篇关摘 · `SU` 主题 · `AU` 作者 · `TS` (WoS topic).

## Skip-expansion rules (phase ③ only)

Default: must expand. Set `"no_expand": true` + `"skip_reason": "<code>"` only
when one of these fires:

| skip_reason | trigger |
|---|---|
| `user_expression` | user supplied a literal boolean expression / query string and asked to use as-is |
| `user_explicit` | user explicitly said "不要扩展 / 别加同义词 / use exactly these terms" |
| `known_id` | DOI / arXiv ID / PMID exact lookup — no search at all |

**Detection signals for `user_expression`**: input contains uppercase
`AND`/`OR`/`NOT`, or field prefixes like `TI=` / `TS=` / `SU=` / `[tiab]`, or
matched parens wrapping boolean phrases. When in doubt, ask the user.

Phases ①②④ are **always required**, even when expansion is skipped — phase ④
must still translate the user's expression into each target DB's syntax.

## Per-DB expression syntax (phase ④)

| db key | syntax | reference |
|---|---|---|
| `gs` | 括号 + 大写 `AND/OR/NOT`，无字段前缀，无字符上限 | `site-patterns/scholar.google.com.md` |
| `cnki` | 专业检索表达式 `TKA=('a'+'b') AND TKA=('c'+'d')`（关键词必用 `TKA`，**禁用 `SU`/`FT`**） | `cnki-delegation.md` + `references/cnki-advanced-search.md` |
| `wos` | `TS=((A OR B) AND (C OR D))` | `wos-delegation.md` |
| `arxiv` | `all:` / `ti:` / `abs:` 前缀 + AND/OR/NOT | `site-patterns/arxiv.org.md` |
| `pubmed` | `(term[tiab] OR term[mh]) AND (...)` | `site-patterns/pubmed.ncbi.nlm.nih.gov.md` |
| `s2` | 关键词串，无布尔（API 限制） | `api-cookbook.md` |

**硬规则**：
- 只有 `cnki` 的 per_db 表达式可以含中文字符，其他库（wos/gs/arxiv/pubmed/s2）必须纯英文/拉丁；validator 会拒（exit 3）。
- `cnki` 的 per_db 表达式**词项必须全部用学术中文**，且**不含任何时间字段**（年度/月/日都不写进表达式）。合法字段码、英→中翻译映射、年度 UI 走位详见 `references/cnki-advanced-search.md` §Arguments + §Step 2.c′。

## 可选字段：质量过滤

`"quality_filter": "high"` —— 用户表达"高水平/顶刊/SCI 分区/核心期刊"等意图时设置。按库分工：
- **WoS**：检索 UI 保持 Core Collection 全 edition 默认。高水平过滤在合并层做——`build_refs.py --high-quality` 只保留 WoS 记录中 CAS25 或 CAS26 分区 ∈ {1区, 2区} 的条目（靠 `journal_lookup.py` 的 ISSN→CAS 分区表）。
- **CNKI**：高水平过滤在结果页"来源类别"锚点区完成，白名单与 UI 序列见 `references/cnki-advanced-search.md` §Step 2.f。
- **arXiv**：`--high-quality` 下全量放行。

无论是否包含 arxiv，触发高水平意图时都设 `quality_filter:"high"` 并给 `build_refs.py` 加 `--high-quality`。

## Plan template

```json
{
  "orig": "用 LLM 做中医实体识别的相关论文",
  "fields": {
    "llm":  {"field": "topic", "terms": ["LLM", "Large Language Model", "大语言模型"]},
    "tcm":  {"field": "topic", "terms": ["TCM", "Traditional Chinese Medicine", "中医", "中药"]},
    "task": {"field": "topic", "terms": ["entity recognition", "实体识别", "命名实体识别"]}
  },
  "boolean": "(llm) AND (tcm) AND (task)",
  "expansion": {
    "llm":  ["LLMs", "Retrieval Augmented Generation"],
    "tcm":  ["Chinese herbal medicine", "中草药"],
    "task": ["entity extraction"]
  },
  "per_db": {
    "gs":   "(LLM OR LLMs OR \"Large Language Model*\") AND (TCM OR \"Traditional Chinese Medicine\" OR \"Chinese herbal medicine\") AND (\"entity recognition\" OR \"entity extraction\")",
    "cnki": "TKA=('大语言模型'+'LLM') AND TKA=('中医'+'中药') AND TKA=('实体识别'+'命名实体识别')",
    "wos":  "TS=((LLM OR \"Large Language Model*\") AND (TCM OR \"Traditional Chinese Medicine\") AND (\"entity recognition\" OR \"entity extraction\"))",
    "s2":   "large language model traditional chinese medicine entity recognition",
    "pubmed": "((large language model[tiab]) AND (traditional chinese medicine[tiab]) AND (entity recognition[tiab]))"
  },
  "databases": ["gs", "cnki", "wos", "s2", "pubmed"],
  "no_expand": false
}
```

## Skip-expansion template

```json
{
  "orig": "(LLM OR \"Large Language Model*\") AND (TCM OR ...) AND (...)",
  "fields":  {"all": {"field": "topic", "terms": ["（用户原式）"]}},
  "boolean": "（用户原式，未改）",
  "per_db":  {"gs": "（原样）", "wos": "TS=((原样))", "cnki": "SU=(...译...)"},
  "databases": ["gs", "wos", "cnki"],
  "no_expand": true,
  "skip_reason": "user_expression"
}
```

## 时间窗过滤策略（per-DB）

能塞服务端就塞，不能的走"宽松服务端 + build_refs 本地裁剪"两段式。

| DB | 服务端粒度 | 写法 | 客户端兜底 |
|---|---|---|---|
| arXiv | 分钟 | 检索式内 `submittedDate:[202601080000 TO 202604082359]` | 无需 |
| PubMed | 天 | 检索式内 `("2026/01/08"[PDAT]:"2026/04/08"[PDAT])` | 无需 |
| WoS | 天 | **独立参数** `DOP=2026-01-08/2026-04-08`，不塞进 TS | 无需 |
| S2 | 年 | API `year=2026` | 按 `publicationDate` 客户端裁剪 |
| CNKI | 年（仅在"出版年度"UI） | 专业检索页"出版年度"两个 `input`（起始/结束年），详见 `references/cnki-advanced-search.md` §Step 2.c′ | **必走** `build_refs.py --start/--end` + cnki 内联导出模板的 `startDate/endDate` 参数按 `td.date` 本地过滤 |
| Google Scholar | 年 | `as_ylo=/as_yhi=` | `--gs-allow-yearonly` 容错 |

原则：`build_refs.py --start/--end` 永远是最终防线；服务端宽松命中后由它裁剪。
