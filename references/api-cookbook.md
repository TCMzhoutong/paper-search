# Academic Platform API Cookbook

各学术平台 API 调用速查。所有示例均可直接复制执行。

---

## arXiv

**根 URL**：`https://export.arxiv.org/api/query`  
**鉴权**：无需  
**格式**：Atom XML  
**速率**：建议 3 秒/请求（非官方限制）

### 检索约定

**默认检索范围：`ti:` + `abs:`**，不使用 `all:`（`all:` 会匹配评论、作者等无关字段，噪音大）。  
多词组合用 `(ti:A OR abs:A) AND (ti:B OR abs:B)` 结构。  
**时间限定必须通过 `submittedDate` 范围参数显式指定**，不能仅靠 `sortBy=submittedDate` 排序替代。

### 搜索

```bash
# 标准查询：标题 OR 摘要，限定近两个月（2026-02-01 ~ 2026-04-06）
curl -s "https://export.arxiv.org/api/query?search_query=(ti:traditional+chinese+medicine+OR+abs:traditional+chinese+medicine)+AND+(ti:artificial+intelligence+OR+abs:artificial+intelligence)+AND+submittedDate:[202602010000+TO+202604060000]&max_results=20&sortBy=submittedDate&sortOrder=descending"

# 多关键词 OR 扩展：覆盖 TCM / Chinese medicine 等同义词
curl -s "https://export.arxiv.org/api/query?search_query=(ti:TCM+OR+ti:%22traditional+chinese+medicine%22+OR+abs:TCM+OR+abs:%22traditional+chinese+medicine%22)+AND+(ti:%22large+language+model%22+OR+abs:%22large+language+model%22+OR+ti:%22deep+learning%22+OR+abs:%22deep+learning%22)&max_results=20&sortBy=submittedDate&sortOrder=descending"

# 按分类 + 标题/摘要（CS.AI 分类内搜索）
curl -s "https://export.arxiv.org/api/query?search_query=(ti:TCM+OR+abs:TCM)+AND+cat:cs.AI&max_results=10&sortBy=submittedDate&sortOrder=descending"

# 按作者搜索
curl -s "https://export.arxiv.org/api/query?search_query=au:Vaswani_A&max_results=20"

# 分页（第 11-20 条）
curl -s "https://export.arxiv.org/api/query?search_query=(ti:diffusion+model+OR+abs:diffusion+model)&start=10&max_results=10&sortBy=submittedDate&sortOrder=descending"
```

**submittedDate 日期范围格式**：`[YYYYMMDDTTTT+TO+YYYYMMDDTTTT]`，时间部分填 `0000` 表示当天起始。  
例：近两个月 → `submittedDate:[202602010000+TO+202604060000]`

**search_query 字段前缀**：

| 前缀 | 说明 | 默认使用 |
|------|------|---------|
| `ti:` | 标题 | ✅ 是 |
| `abs:` | 摘要 | ✅ 是 |
| `au:` | 作者（格式：`LastName_FirstInitial`） | 按需 |
| `cat:` | 分类（如 `cs.AI`、`cs.LG`、`stat.ML`） | 按需 |
| `all:` | 全字段搜索 | ❌ 避免使用（噪音大） |

**响应字段映射**（Atom XML `<entry>` 节点）：

| XML 路径 | 标准字段 |
|---------|---------|
| `<title>` | title |
| `<author><name>` | authors[] |
| `<summary>` | abstract |
| `<published>` | year（取前 4 位） |
| `<arxiv:doi>` | doi |
| `<id>`（末段） | arxiv_id |
| `<link rel="related" type="application/pdf" href>` | pdf_url |

**PDF 直链规律**：`https://arxiv.org/pdf/{arxiv_id}` （如 `https://arxiv.org/pdf/2301.00001`）

**批量 PDF 下载**：拿到 Atom XML 后用 canonical 脚本 `scripts/download_arxiv.py <arxiv.xml> [out_dir]`。脚本按 `{FirstAuthorSurname}_{Year}_{ShortTitle}.pdf` 命名，节流 3 s/篇，默认 out_dir = `<arxiv.xml>` 的父目录（即 `paper_raw/`）。

**BibTeX 导出**：`https://arxiv.org/bibtex/{arxiv_id}`

---

## Semantic Scholar

**根 URL**：`https://api.semanticscholar.org/graph/v1`  
**鉴权**：Header `x-api-key: YOUR_KEY`（免费注册，高频必需；低频可不加 Key）  
**格式**：JSON  
**速率**：无 Key 约 100 req/5min；有 Key 1 req/s

### 搜索论文

```bash
# 关键词搜索（返回指定字段）
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=attention+is+all+you+need&fields=title,authors,year,abstract,citationCount,externalIds,openAccessPdf&limit=10" \
  -H "x-api-key: YOUR_KEY"

# 按 DOI 查询单篇
curl -s "https://api.semanticscholar.org/graph/v1/paper/DOI:10.18653/v1/P16-1162?fields=title,authors,abstract,citationCount,openAccessPdf" \
  -H "x-api-key: YOUR_KEY"

# 按 arXiv ID 查询
curl -s "https://api.semanticscholar.org/graph/v1/paper/ARXIV:1706.03762?fields=title,authors,year,citationCount,openAccessPdf" \
  -H "x-api-key: YOUR_KEY"

# 批量查询（POST，最多 500 篇）
curl -s -X POST "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,citationCount" \
  -H "Content-Type: application/json" \
  -d '{"ids":["DOI:10.xxx/xxx","ARXIV:2301.00001"]}' \
  -H "x-api-key: YOUR_KEY"
```

### 作者查询

```bash
# 按作者名搜索
curl -s "https://api.semanticscholar.org/graph/v1/author/search?query=Yann+LeCun&fields=name,affiliations,paperCount,citationCount" \
  -H "x-api-key: YOUR_KEY"

# 获取作者全部论文
curl -s "https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,year,citationCount&limit=100" \
  -H "x-api-key: YOUR_KEY"
```

### 引用/被引

```bash
# 获取引用该论文的文章
curl -s "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations?fields=title,year,authors&limit=50" \
  -H "x-api-key: YOUR_KEY"

# 获取该论文引用的文章
curl -s "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references?fields=title,year,authors&limit=50" \
  -H "x-api-key: YOUR_KEY"
```

**响应字段映射**：

| JSON 字段 | 标准字段 |
|-----------|---------|
| `title` | title |
| `authors[].name` | authors[] |
| `year` | year |
| `abstract` | abstract |
| `citationCount` | citation_count |
| `externalIds.DOI` | doi |
| `externalIds.ArXiv` | arxiv_id |
| `openAccessPdf.url` | pdf_url |

**注意**：`fields` 参数必须显式指定，否则默认只返回 `paperId` 和 `title`。

---

## PubMed（NCBI E-utilities）

**根 URL**：`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`  
**鉴权**：无需（有 API Key 可提升速率）  
**格式**：XML / JSON  
**速率**：无 Key 3 req/s；有 Key 10 req/s；请求加 `&email=your@email.com`

### 检索约定

**默认检索字段：`[Title/Abstract]`**，不使用裸关键词（裸词会触发 PubMed 自动扩展到 MeSH，范围过宽、噪音大）。  
MeSH 词作为**补充扩展**与 `[Title/Abstract]` 用 OR 组合，而非单独使用。  
**时间限定必须通过 `datetype=pdat&mindate=&maxdate=` 参数显式指定**，不能省略。

### 三步流程

```bash
# Step 1：esearch — 搜索，获取 PMID 列表
# 标准格式：字段限定 [Title/Abstract] + 日期范围（必填）
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=(traditional+chinese+medicine[Title/Abstract]+OR+TCM[Title/Abstract])+AND+(artificial+intelligence[Title/Abstract]+OR+machine+learning[Title/Abstract]+OR+deep+learning[Title/Abstract]+OR+large+language+model[Title/Abstract])&datetype=pdat&mindate=2026/02/01&maxdate=2026/04/06&retmax=30&retmode=json&email=your@email.com"

# MeSH 补充扩展示例（与 Title/Abstract 并用）
# term=(... [Title/Abstract]) OR ("Medicine, Chinese Traditional"[MeSH] AND "Artificial Intelligence"[MeSH])

# Step 2：esummary — 按 PMID 批量获取元数据（JSON，轻量，第一遍扫描用）
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=12345678,23456789&retmode=json&email=your@email.com"

# Step 3：efetch — 获取完整摘要正文（XML，第二遍深挖用）
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=12345678,23456789&rettype=abstract&retmode=xml&email=your@email.com"

# Step 4（可选）：elink — 获取相关文献
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pubmed&id=12345678&linkname=pubmed_pubmed&retmode=json&email=your@email.com"
```

**日期参数说明**：

| 参数 | 说明 |
|------|------|
| `datetype=pdat` | 按发表日期筛选（edat=入库日期，pdat=发表日期，优先用 pdat） |
| `mindate=YYYY/MM/DD` | 起始日期（含） |
| `maxdate=YYYY/MM/DD` | 截止日期（含） |

**元数据/摘要获取**（`esummary` 返回 JSON DocSum 元数据；需要摘要正文时改用 `efetch` XML）：

```bash
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=12345678&retmode=json&email=your@email.com"
```

**响应字段映射**（`esummary` / DocSum JSON）：

| JSON 字段 | 标准字段 |
|-----------|---------|
| `result[pmid].title` | title |
| `result[pmid].authors[].name` | authors[] |
| `result[pmid].pubdate`（前 4 位） | year |
| `result[pmid].source` | venue |
| `result[pmid].articleids[type=doi].value` | doi |
| `result[pmid].uid` | pubmed_id |

---

## Papers with Code

**根 URL**：`https://paperswithcode.com/api/v1`  
**鉴权**：无需  
**格式**：JSON  
**速率**：无官方说明，适度使用

```bash
# 搜索论文
curl -s "https://paperswithcode.com/api/v1/papers/?q=object+detection&items_per_page=10"

# 获取论文详情
curl -s "https://paperswithcode.com/api/v1/papers/{paper_id}/"

# 获取论文对应代码仓库
curl -s "https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/"

# 获取论文在 benchmark 上的结果
curl -s "https://paperswithcode.com/api/v1/papers/{paper_id}/results/"

# 按方法搜索
curl -s "https://paperswithcode.com/api/v1/methods/?q=transformer"
```

**响应字段映射**：

| JSON 字段 | 标准字段 |
|-----------|---------|
| `title` | title |
| `authors` | authors[] |
| `published` | year（前 4 位） |
| `abstract` | abstract |
| `arxiv_id` | arxiv_id |
| `url_pdf` | pdf_url |

**独特价值**：`repositories` 端点可直接获取论文对应 GitHub 仓库（stars、框架、官方/非官方标注）。

---

## ACM Digital Library

**官方 API**：无公开免费 API  
**推荐方式**：WebFetch + Jina，或 CDP  
**DOI 前缀**：`10.1145/`

```bash
# 通过 DOI 获取页面（Jina 转 Markdown）
curl -s "https://r.jina.ai/dl.acm.org/doi/10.1145/3292500.3330701"

# 获取 BibTeX（无需登录）
curl -s "https://dl.acm.org/action/exportCitation?doi=10.1145%2F3292500.3330701&format=bibtex&downloadName=acm-bibtex"

# 直接访问 DOI 页面（JSON-LD 含结构化元数据）
curl -s "https://dl.acm.org/doi/10.1145/3292500.3330701" | grep -o '"@type".*"Article"[^}]*}'
```

**BibTeX 导出 URL 格式**：
```
https://dl.acm.org/action/exportCitation?doi={URL编码后的DOI}&format=bibtex
```
DOI 中的 `/` 编码为 `%2F`。

**注意**：该端点在部分网络环境下会返回 Cloudflare challenge 或 HTML 错页，不一定稳定；若未返回 BibTeX 文本，改用 CDP 点击页面上的导出按钮。

**JSON-LD 提取**（页面 `<script type="application/ld+json">` 中）：含 `name`（标题）、`author`、`datePublished`、`description`（摘要）。

---

## IEEE Xplore

**官方 API**：需机构订阅 Key（`https://developer.ieee.org`）  
**无 Key 时**：WebFetch / Jina 抓公开摘要页  
**文章 URL 格式**：`https://ieeexplore.ieee.org/document/{arnumber}/`

```bash
# 有 Key 时：搜索 API
curl -s "https://ieeexploreapi.ieee.org/api/v1/search/articles?querytext=deep+learning&max_records=10&apikey=YOUR_KEY"

# 无 Key：Jina 抓摘要页
curl -s "https://r.jina.ai/ieeexplore.ieee.org/document/9607200/"

# 直接抓页面（JSON-LD 在 <script> 中）
curl -s -A "Mozilla/5.0" "https://ieeexplore.ieee.org/document/9607200/"
```

**有 Key 时响应字段映射**：

| JSON 字段 | 标准字段 |
|-----------|---------|
| `title` | title |
| `authors.authors[].full_name` | authors[] |
| `publication_year` | year |
| `abstract` | abstract |
| `doi` | doi |
| `pdf_url` | pdf_url |
| `article_number` | ieee_id |

---

## Google Scholar

**官方 API**：无  
**唯一可靠方式**：CDP 浏览器自动化（直连用户 Chrome）  
**不要尝试**：WebFetch、curl、WebSearch 搜索 scholar.google.com

### CDP 操作流程

```bash
# 1. 确保 CDP Proxy 就绪（默认 127.0.0.1:3456，手动启动 scripts/cdp-proxy.mjs 即可）
# 2. 打开 Google Scholar 搜索页
TARGET=$(curl -s "http://127.0.0.1:${CDP_PROXY_PORT:-3456}/new?url=https://scholar.google.com" | node -p "JSON.parse(require('fs').readFileSync(0, 'utf8')).targetId")

# 3. 用搜索框搜索（GUI 方式，最稳定）
curl -s -X POST "http://127.0.0.1:${CDP_PROXY_PORT:-3456}/eval?target=$TARGET" \
  -d 'document.querySelector("input[name=q]").value = "attention is all you need"'
curl -s -X POST "http://127.0.0.1:${CDP_PROXY_PORT:-3456}/click?target=$TARGET" -d 'button[type=submit], input[type=submit]'

# 4. 等待结果加载后提取
curl -s -X POST "http://127.0.0.1:${CDP_PROXY_PORT:-3456}/eval?target=$TARGET" -d '
JSON.stringify(Array.from(document.querySelectorAll(".gs_ri")).slice(0,10).map(el => ({
  title: el.querySelector(".gs_rt a")?.textContent?.trim(),
  link: el.querySelector(".gs_rt a")?.href,
  authors_venue: el.querySelector(".gs_a")?.textContent?.trim(),
  cited_by: el.querySelector(".gs_fl a")?.textContent?.match(/Cited by (\d+)/)?.[1]
})))
'

# 5. 完成后关闭 tab
curl -s "http://127.0.0.1:${CDP_PROXY_PORT:-3456}/close?target=$TARGET"
```

**主要用途**：获取引用数（Scholar 引用数最全面）、发现其他平台未收录的论文、查看相关论文推荐。

**注意**：操作间隔不要过短，避免触发 CAPTCHA。详见 `site-patterns/scholar.google.com.md`。

---

## CNKI（中国知网）

> **⚠️ 本节不提供直接操作指令**。CNKI 所有检索任务统一委托给专用的 **cnki-* skills**，不在此重复 CDP 操作细节。

### 任务委托规则

| 任务 | 调用的 skill |
|------|-------------|
| 期刊精确检索（含来源类别筛选） | 读 `references/cnki-advanced-search.md` 内联执行 |
| 学位论文检索 | 读 `references/cnki-advanced-search.md` 内联执行 → 结果页点"学位论文"tab |
| 导出 RIS（含摘要/关键词/DOI） | 编排层在结果页 `evaluate_script` 内联执行 `dm8/API/GetExport` 模板（见 `references/cnki-delegation.md` §合并管道） |
| 下载全文 | 读 `references/cnki-download.md` 内联执行 |

### 检索约定（执行时必须遵守）

- **字段（硬规则）**：**关键词一律使用 `TKA`（篇关摘）**。禁用 `SU`（主题，命中全文主题标注噪音）、`FT`（全文，噪音更大）
- **期刊**：按 `references/cnki-advanced-search.md` 内联执行时指定来源类别 SCI/EI/CSSCI/北大核心/CSCD
- **学位论文**：按 `references/cnki-advanced-search.md` 内联执行检索后在结果页**点击"学位论文"tab**；**不可用 `crossids` URL 参数**（触发验证码/暂无数据）
- **时间**：必须显式指定，不可省略

详细操作模式见 `references/cnki-delegation.md` 与 `references/cnki-advanced-search.md`。
