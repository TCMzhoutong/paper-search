---
name: paper-search
description: |
  学术论文搜索、引用分析与元数据提取专用 Skill。

  【自动触发条件——出现以下任一信号时立即加载本 Skill，无需用户显式说明】

  意图信号（中文）：
  - 搜论文 / 找论文 / 查论文 / 调研论文 / 检索文献 / 文献综述 / 综述
  - 顶会 / 顶刊 / CCF / NeurIPS / ICML / ICLR / ACL / EMNLP / CVPR / KDD / SIGIR / WWW
  - 引用数 / 被引 / 引用关系 / 引用量
  - BibTeX / 参考文献格式 / 导出引用
  - 作者发表列表 / 某人的论文 / 某人在哪发了什么
  - arXiv / Semantic Scholar / Google Scholar / PubMed / ACM DL / IEEE
  - 知网 / CNKI / 中国知网 / 学位论文 / 硕士论文 / 博士论文 / 中文文献 / 中文期刊
  - Web of Science / WoS / SCI / SSCI / JCR / 影响因子
  - PDF 链接 / 论文 PDF / 开放获取
  - 摘要 abstract / 元数据

  意图信号（英文）：
  - search paper / find paper / look up paper / literature review / survey
  - citation count / citation graph / citing / cited by
  - BibTeX / reference export
  - top conference / top journal / venue ranking
  - author publication list / papers by X

  URL 信号（出现以下域名的链接时自动触发）：
  - arxiv.org / ar5iv.org
  - semanticscholar.org
  - scholar.google.com
  - dl.acm.org
  - ieeexplore.ieee.org
  - pubmed.ncbi.nlm.nih.gov
  - paperswithcode.com
  - cnki.net / kns.cnki.net
  - webofscience.com（含机构 VPN 反代 host，见 `config.md`）

  覆盖平台：arXiv、Semantic Scholar、Google Scholar、ACM DL、IEEE Xplore、PubMed、Papers with Code、CNKI、Web of Science
metadata:
  version: "2.0.0"
---

# paper-search Skill

本 skill 是文献检索的**编排层**。所有数据库操作由 leaf skill 或 API 完成，本 skill 只负责：意图路由 → query 扩展 → 调度 → 落 `paper_raw/_tmp/` → `build_refs` 合并 → 按需下载 PDF。

## 个人配置

所有 API Key / 邮箱 / 反代 host 见 `config.md`。S2 调用必须加 `-H "x-api-key: $S2_API_KEY"`。

## 平台选择矩阵

### 数据库选择规则（硬规则）

- **用户显式列出数据库** → 只跑列出的库；库挂了报告给用户，不用其他库兜底。
- **用户未指定** → 走下方"默认并行"+"按需加入"矩阵自主选。

*Rationale*：用户列出库 = 对来源（出版类型/质量/语言/订阅）的显式选择。

---

**默认并行**（用户未指定时）：arXiv、Semantic Scholar（REST API）

**按需加入**（用户未指定时）：

| 需求 | 平台 | 访问 / 委托 | 触发 |
|------|------|---------|------|
| 生物医学 | PubMed | NCBI E-utilities | 医学/生物/临床/药物/基因 |
| 代码仓库 | Papers with Code | REST API | 复现/开源实现 |
| CS 顶会 BibTeX | ACM DL | WebFetch + Jina | 明确提 ACM |
| IEEE 论文 | IEEE Xplore | WebFetch / Jina | 明确提 IEEE |
| 全平台引用数 | Google Scholar | **CDP**（必须） | 明确提 Scholar |
| 中文文献 | CNKI | 编排层 **Read** `references/cnki-delegation.md` + `references/cnki-advanced-search.md` + `references/cnki-download.md` **内联执行** chrome-devtools | 知网/CNKI/中文 |
| SCI/SSCI/JCR | Web of Science | 编排层 **Read** `references/wos-delegation.md` + `references/wos-download.md` **内联执行** chrome-devtools | WoS/SCI/影响因子 |

API 细节见 `references/api-cookbook.md`。CDP 操作见 `references/cdp-api.md`。

## 核心流程

1. **Query 扩展**：在响应里直接给出每个目标库的最终检索式（一张 markdown 表：`db | expression`）。同义词/双语/字段映射自然推理，不必走脚本 gate。
   - 跳过扩展的 3 种情况：用户给了字面表达式 / 用户明说不要扩展 / DOI/arXiv ID/PMID 精确查找——此时只需把原式按各库语法翻译一次
   - 用户说"高水平/顶刊/SCI 分区/Q1 Q2/核心期刊" → 设 `quality_filter:"high"`，WoS 走 SCI/SSCI edition，build_refs 加 `--high-quality`（CNKI 具体 UI 序列见 `references/cnki-advanced-search.md`，语义见 `references/query-plan.md` §质量过滤）
   - 时间窗 per-DB 写法（服务端粒度 + 客户端兜底）见 `references/query-plan.md` §时间窗过滤策略
   - 复杂场景或想要可校验的 plan：可选 `scripts/expand_queries.py --plan plan.json`（见 `references/query-plan.md`），并设 `PAPER_SEARCH_GATE=1` 让 build_refs 强制校验
   - per-DB 语法速查见 `references/query-plan.md` 的"Per-DB expression syntax"表
2. **调度**：API 库并行（arxiv/s2/pubmed），浏览器库（cnki/wos/gs）逐个串行——见硬规则节
3. **落 per-source 中间件到 `paper_raw/_tmp/{db}.{xml,json,ris,jsonl}`**（写入责任分三路）：
   - **API 库**（arXiv/S2/PubMed/PwC）：编排层 `curl -o` 直接落盘
   - **CNKI**：编排层 Read `references/cnki-advanced-search.md` + `cnki-delegation.md` §合并管道，按指引内联执行 chrome-devtools 检索 + 在结果页 `evaluate_script` 跑 `dm8/API/GetExport` blob 导出到 `~/Downloads/cnki.ris`，再 `mv` 到 `_tmp/cnki.ris`
   - **WoS**：编排层 Read `references/wos-delegation.md`，按 §检索流程 + §合并管道 内联执行 chrome-devtools（navigate 到 VPN 反代 `/wos/woscc/advanced-search` → 粘贴表达式 → 点 Search → 结果页触发 `Export → Plain text file` UI，Record Content = `Author, Title, Source, Abstract`），浏览器下载到 `~/Downloads/savedrecs.txt` 后 `mv` 到 `_tmp/wos.txt`
   - 任何情况下都不直接写终件 `refs.ris`
4. **合并**：`scripts/build_refs.py` 读 `_tmp/*` → 跨源去重（DOI > arXiv ID > WoS ID > title+year 模糊匹配）→ 写终件 `refs.ris` + `summary.md`
5. **按需下载 PDF**（用户明确说"下载"时），落 `paper_raw/{first_author}_{year}_{short_title}.pdf`

## 输出三件套（每次检索默认产出）

所有文件落在当前工作目录下的 `./paper_raw/`（不存在则创建）。

**终态定义**（任务完成时 `paper_raw/` 下**有且仅有**）：

```
paper_raw/
├── refs.ris          # 跨源合并去重后的唯一 RIS
├── summary.md        # 跨源合并表，按发表日期倒序
├── {Author}_{Year}_{Title}.pdf × N   # 仅用户说"下载"时产出
└── _tmp/             # per-source 中间件，build_refs 合并后可删
    ├── arxiv.xml
    ├── wos.ris
    └── cnki.ris
```

**per-source 文件（如 `refs_wos.ris` / `summary_cnki.md`）属于临时产物，不能作为终件交付**；必须经 `scripts/build_refs.py` 合并为 `refs.ris` + `summary.md` 才算任务完成。

**合并管道**：各来源原始响应落 `paper_raw/_tmp/{db}.{xml,json,ris,jsonl}`（写入责任见核心流程 Step 3），统一由 `scripts/build_refs.py` 解析 + 跨源去重 + 日期过滤，输出终件。

### 1. `paper_raw/refs.ris` — RIS 引文文件

- `DO` 字段写 DOI（任何来源有 DOI 都写）
- `L1` 字段指向本地已下载 PDF 的 `file:///...` 绝对路径。`build_refs.py` 在合并阶段按 `{source, first_author, year, title}` 匹配 `paper_raw/` 下的 PDF：命中写入 `L1`，未命中则该记录无 `L1`（EndNote 导入时仅载元数据）。

### 2. `paper_raw/summary.md` — 结果 Markdown 表格

字段列（必须）：`题目 | 发表日期 | 年份 | 作者 | 期刊/来源 | JCR | 中科25 | 中科26 | 关键词 | 摘要`

- **发表日期**：ISO `YYYY-MM-DD`；数据源只给年份时兜底 `YYYY-01-01`
- 作者超过 3 人用"张三 等"
- 摘要保留完整（md 表格用 `<br>` 或折叠）
- 按发表日期倒序

### 3. `paper_raw/{first_author}_{year}_{short_title}.pdf` — 原文（仅用户明确说"下载"时生成）

**判断标准**：用户消息包含"下载"、"下载 PDF"、"下载全文"、"保存到本地"才触发。

- arXiv：`curl` 直取（唯一允许编排层直接下载的来源）
- **CNKI / WoS / 其他浏览器驱动来源**：编排层在**同一会话、同一浏览器上下文**内，**Read 对应 reference doc 并按指引内联执行** chrome-devtools，完成"检索 → 导 RIS → 逐篇下载 PDF"。每篇 PDF 前 Read `references/cnki-download.md` / `references/wos-download.md` 获取下载步骤。严禁：(a) 用 Agent 工具 + `general-purpose` 包装并让 sub-agent 自写 UI 序列；(b) A 库搜 → B 库搜 → A 库下 → B 库下 交叉（chrome-devtools 全局页状态会丢 cookie / 触发 VPN 重登）；(c) 试图用 `Skill(cnki-advanced-search)` 等形式调用——**这些不是已注册的顶层 skill**，Skill 工具会返回 `Unknown skill`。
- **不尝试**绕过付费墙

## 精确论文查找（已知 DOI 或 arXiv ID）

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,authors,year,abstract,citationCount,openAccessPdf" -H "x-api-key: ..."
curl -s "https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}?fields=..." -H "x-api-key: ..."
```

## 失败信号速查

| 信号 | 方向 |
|---|---|
| API 429 | 等 15s+ 或切 CDP，不要同请求重试 |
| arXiv 301 / 空 body | curl 必须加 `-L` 跟随重定向 |
| arXiv 503 | 等 60–90s；时间窗用 `submittedDate:[...]` 而非主题词+客户端过滤 |
| S2 空结果 | 换关键词组合或换 arXiv/PubMed |
| CNKI 滑块 / GS reCAPTCHA | **立即停手**报告用户人工解，不要重试（反爬冷却 ≥ 5 min） |
| 同方式重试 3 次无改善 | 路径错了；换平台/访问方式 |

## 硬规则

- **枚举规则不扩展**：skill 文档用枚举列表定义白名单/集合/阈值时按列表执行。UI 面板里出现列表外的选项不勾；觉得有缺漏，先回复里提出让用户拍板。判别"规则 vs 示例"：`=`/列表/"必须"/"白名单"是规则；"例如"/"如..."/"可以"是示例。
- **chrome-devtools MCP 强制串行**：CNKI/WoS/GS 逐个委托，不可并发；每次 `evaluate_script` 用 `location.href` 校验 hostname。（根因：MCP 全局"当前页"状态竞态。要并行换 `playwright-cli`。）
- **浏览器库 = Read reference doc 并内联执行，不是 Skill 工具，也不是 Agent 工具**：CNKI/WoS/GS 的"检索 + 导 RIS + 下载"没有已注册的 leaf skill。编排层**直接** Read 对应 reference doc（如 `references/cnki-advanced-search.md` → `cnki-delegation.md` §合并管道的 `dm8/API/GetExport` JS 模板 → `references/cnki-download.md`）按指引**内联**执行 chrome-devtools MCP 调用。**严禁**：(a) `Skill(cnki-advanced-search)` / `Skill(wos-search)` 这种调用——它们从未注册为顶层 skill，运行时会 `Unknown skill`；(b) 用 Agent 工具 + `general-purpose` 包一层 sub-agent 自写 UI 序列——那会绕过 reference doc 里的既定 UI 序列和权威导出管道，并引入虚构 subagent_type。
- **中间件路径 = `paper_raw/_tmp/`**：所有 per-source 中间件（`arxiv.xml` / `wos.ris` / `cnki.ris` 等）落在当前工作目录下 `paper_raw/_tmp/`。任务产物自包含、不同检索任务互不污染、用户可直接检视。`build_refs.py` 从 `paper_raw/_tmp/` 读入，合并后原始中间件可保留可删。

## References 索引

| 文件 | 何时加载 |
|------|---------|
| `references/query-plan.md` | 查 per-DB 语法速查表；或可选构建结构化 4 阶段 plan |
| `references/cnki-delegation.md` | CNKI 相关任一操作 |
| `references/wos-delegation.md` | WoS 相关任一操作 |
| `references/api-cookbook.md` | arXiv/S2/PubMed/PwC API 调用模板 |
| `references/cdp-api.md` | Google Scholar 等需要浏览器自动化时 |
| `references/parallel.md` | API 库（arxiv/s2/pubmed）多 query 分治时；**浏览器库不适用** |
| `references/site-patterns/{domain}.md` | 具体站点经验（按域名） |
