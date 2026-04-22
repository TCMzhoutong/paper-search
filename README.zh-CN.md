<p align="right">🌐 简体中文 | <a href="README.md">English</a></p>

# paper-search

Claude Code skill，用于跨 **arXiv、Semantic Scholar、Google Scholar、PubMed、ACM DL、IEEE Xplore、Papers with Code、CNKI（知网）、Web of Science** 九大平台做学术论文搜索、引用分析与元数据提取。每次检索产出一份跨源合并去重的 `refs.ris` 和一张 `summary.md` 表格。

## 致谢

本项目改自 [ustc-ai4science/academic-search](https://github.com/ustc-ai4science/academic-search)（作者 **Chengmingyue**，MIT 协议）。`SKILL.md` 的编排骨架、`scripts/cdp-proxy.mjs` 的 CDP 代理、`references/api-cookbook.md` 的 API 手册、以及 arXiv / Semantic Scholar / Google Scholar / PubMed / ACM DL / IEEE / Papers with Code 的 site-pattern 笔记都源自上游项目，继续按上游 MIT 协议分发。

逐文件的归属明细见 [`NOTICE`](NOTICE)；协议条款（同时覆盖上游代码与本 fork 的新增内容）见 [`LICENSE`](LICENSE)。

如果你觉得本 fork 有用，也请去上游仓库点个 star。

## 安装

```bash
git clone https://github.com/TCMzhoutong/paper-search ~/.claude/skills/paper-search
```

然后在本地按 `config.md` 模板填入自己的 key / 邮箱 / host（**不要**把真实值 commit 回仓库）。

账号 / 凭据：
- **Semantic Scholar API Key**（可选但强烈建议，能显著提高速率上限）—— https://www.semanticscholar.org/product/api
- **Unpaywall 邮箱**（必填，`scripts/wos_oa_download.py` 查 OA PDF 时要用）
- **CNKI / Web of Science 访问权**（机构 IP 白名单或 VPN 反代；仅当你要查这两个库时需要）

环境变量：

```bash
export S2_API_KEY="<你的 S2 API Key>"
export PAPER_SEARCH_EMAIL="<你的邮箱@example.com>"
```

## 使用

在 Claude Code 里随便说一句 skill frontmatter 里列出的中文或英文检索意图词即可自动触发。典型一句话：

> 搜一下 2024-2026 年 GraphRAG 的综述，arXiv + Semantic Scholar，最多 30 条

产物落在当前工作目录下的 `./paper_raw/`：

```
paper_raw/
├── refs.ris          # 跨源合并去重的 RIS（DOI > arXiv ID > WoS ID > 题名+年份 模糊匹配）
├── summary.md        # 按发表日期倒序的 markdown 表
└── _tmp/             # per-source 中间件，合并后可删
```

完整编排规则见 [`SKILL.md`](SKILL.md)，各数据库细节见 [`references/`](references/)。

## 与上游的差异

本节逐条列出对 [`ustc-ai4science/academic-search`](https://github.com/ustc-ai4science/academic-search)（基线 commit `df71ccc`）的改动。逐文件归属见 [`NOTICE`](NOTICE)。

### 1. 改名与归属

- skill 改名 `academic-search` → `paper-search`；`SKILL.md` frontmatter 的 `version` 升到 `2.0.0`。
- 环境变量改名：`ACADEMIC_SEARCH_EMAIL` → `PAPER_SEARCH_EMAIL`，`ACADEMIC_SEARCH_GATE` → `PAPER_SEARCH_GATE`。
- `LICENSE` 改为双版权 MIT（Chengmingyue 2026 + Tong Zhou 2026）。
- 新增 `NOTICE` 给出文件级归属。
- 新增 `README.md` + `README.zh-CN.md`，替换上游的营销向 README。

### 2. 交付契约

上游让模型自由输出各平台的 RIS / JSON / Markdown；本 fork 固化为**三件套契约**，强制每次检索都产出，路径固定为当前工作目录下的 `./paper_raw/`：

```
paper_raw/
├── refs.ris          # 跨源合并去重
├── summary.md        # 按发表日期倒序的 markdown 表，字段固定
├── _tmp/             # per-source 中间件（arxiv.xml / s2.json / cnki.ris / wos.txt / ...）
└── {Author}_{Year}_{Title}.pdf × N   # 仅当用户显式说"下载"时产出
```

`summary.md` 字段固定：`题目 | 发表日期 | 年份 | 作者 | 期刊/来源 | JCR | 中科25 | 中科26 | 关键词 | 摘要`，`发表日期` 用 ISO `YYYY-MM-DD`（数据源只给年份时兜底 `YYYY-01-01`）。

### 3. 新增跨源合并器 —— `scripts/build_refs.py`（约 664 行）

读 `paper_raw/_tmp/{arxiv.xml, s2.json, pubmed.xml, pwc.json, cnki.ris, wos.txt, ...}`，按 **DOI > arXiv ID > WoS ID > 题名+年份 模糊匹配** 的优先级跨源去重，产出终件 `refs.ris`（任一来源有 DOI 就写 `DO` 字段；本地下载了 PDF 就写 `L1` 字段指向本地文件），并渲染 `summary.md`。

### 4. 结构化查询计划 —— `references/query-plan.md` + `scripts/expand_queries.py`（约 249 行）

四阶段计划（意图识别 → 概念分解 → per-DB 检索式合成 → 执行调度），带可选 JSON schema。`scripts/expand_queries.py` 校验一份 plan；把 `PAPER_SEARCH_GATE=1` 设为环境变量时，`build_refs.py` 会强制校验通过才允许合并。文档内含 per-DB 语法速查（arXiv `ti:`+`abs:` + `submittedDate:`、S2 `query`、PubMed `[Title/Abstract]` + `datetype=pdat`、WoS `TS=`、CNKI `TKA=`、Google Scholar 嵌套布尔）。

### 5. 数据库选择规则硬化

- **硬规则**：用户显式列库 → 只跑列出的库；库挂了报告用户，**不用**其他库兜底。
- 新增"默认并行 / 按需加入"矩阵：arXiv + Semantic Scholar 默认并行；PubMed / Papers with Code / ACM DL / IEEE / GS / CNKI / WoS 按意图信号按需加入。
- **浏览器驱动库（CNKI、WoS、GS）强制串行**：chrome-devtools MCP 有单个全局"当前页"状态，并发会破坏 cookie / 触发 VPN 重登。`references/parallel.md` 记录该约束和 API 侧并行模式。

### 6. CNKI 流水线（新增，约 356 行）

上游只有一个简短的 `cnki.net` site-pattern。本 fork 替换为完整流水线：

- `references/cnki-advanced-search.md` —— CNKI 专业检索表达式语言（`TKA=` 字段码、`+` / `*` / `%` 运算符、学术中文词项对照表）。
- `references/cnki-delegation.md` —— 委托契约 + `dm8/API/GetExport` JS 模板（把结果页直接导成 RIS blob，存到 `paper_raw/_tmp/cnki.ris`）。
- `references/cnki-download.md` —— 逐篇 PDF 下载 UI 序列。
- `config.md` 加入机构 VPN 反代 host（模板占位，填你自己的）。

### 7. Web of Science 流水线（新增，约 107 行）

上游**完全不支持** WoS。本 fork 补齐：

- `references/wos-delegation.md` —— VPN 路由规则、高级检索流程、`TS=` 表达式语法、死节点 503 后的会话恢复。
- `references/wos-download.md` —— `Export → Plain text file` 导出流程、Unpaywall 查 OA PDF 的二次下载。
- `scripts/wos_oa_download.py`（约 95 行）—— 按 DOI 查 Unpaywall，有 OA 就下载。

### 8. 期刊质量元数据 —— `data/jcr.db` + `scripts/journal_lookup.py`

16 MB 的 SQLite 数据库，装载 Journal Citation Report 元数据。`scripts/journal_lookup.py`（约 141 行）接受期刊名或 ISSN，返回 JCR 分区、中科院分区（2025 / 2026 双年份）、影响因子；`build_refs.py` 在渲染 `summary.md` 时调用它。

### 9. arXiv 批量下载 —— `scripts/download_arxiv.py`（约 79 行）

解析 arXiv Atom XML，按 `{首作者姓}_{年份}_{短题名}.pdf` 命名逐篇下载，严格遵守 3 秒 / 篇的节流。仅在用户显式说"下载" / "download" 时触发。

### 10. 个人配置单一事实来源 —— `config.md`

上游不硬编码任何 key，但也没提供统一的存放地。本 fork 加入 `config.md` 模板，文档化所有占位符（`{S2_API_KEY}` / `{UNPAYWALL_EMAIL}` / `{CNKI_HOST}` / `{WOS_HOST}`）与对应环境变量（`S2_API_KEY`、`PAPER_SEARCH_EMAIL`）。文件已脱敏 —— 不 commit 任何真实 key / 邮箱 / 机构 VPN host。`.gitignore` 增补了 `config.local.md` / `.env*` / `paper_raw/` 等忽略规则。

### 11. `SKILL.md` 重写为纯编排层

上游 `SKILL.md` 约 323 行，含大段"搜索哲学"前言（成功标准、两遍扫描、失败信号表）。本 fork 压缩到约 173 行：

- 删掉 `check-deps.sh` 前置检查段。
- 把平台选择表换成上文 §5 的"默认并行 / 按需加入"矩阵。
- 所有 CNKI / WoS / GS 工作委托到对应 reference 文档（内联执行 chrome-devtools MCP，不套 sub-agent）。
- 明确固化 `paper_raw/_tmp/` 中间件路径。
- 新增"硬规则"节（枚举规则不可扩展、浏览器库强制串行、`Skill(cnki-advanced-search)` **不是**已注册的顶层 skill —— reference 文档要 Read 并内联执行）。

### 12. Site-pattern 扩展

- `references/site-patterns/arxiv.org.md` —— 追加 2026-04-07 的 Varnish 429/503 冷却观察（60–90 s，重试无法缩短），并把时间窗推荐改为 `submittedDate:[...]` 范围语法。
- `references/site-patterns/scholar.google.com.md` —— 新增"检索式构建"节（无字段前缀的嵌套布尔、短语引号、多概念实例）与"时间筛选"节（GS 缺少可靠月份字段）。

### 13. 未继承的上游文件

`Makefile`、`agents/openai.yaml`、`assets/*`、`docs/skill-usage-comparison.md`、`wechat-promo.md`、`scripts/check-deps.sh`、`scripts/release-test.sh`、`scripts/self-test.sh`、`references/metadata-schema.md`、`references/venue-rankings.md`、`references/site-patterns/cnki.net.md`、`README.en.md`。原因见 `NOTICE`。

## 协议

MIT —— 见 [`LICENSE`](LICENSE)。保留 **Chengmingyue (2026)** 对上游部分的原始版权，并为本 fork 的修改追加 **Tong Zhou (2026)** 版权。
