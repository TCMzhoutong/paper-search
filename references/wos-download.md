# WoS 全文 PDF 下载

## 核心模式

纯文件管道，**不走浏览器循环**：

1. 从 `paper_raw/_tmp/wos.txt`（`wos-delegation.md` §合并管道 产出的 Plain text 导出）里提取 DOI。
2. 对每个 DOI 调 `api.unpaywall.org/v2/{doi}`。保留 `is_oa == true` 且 `best_oa_location.url_for_pdf` 非空的记录。
3. `urllib.request` / `curl` 按 `url_for_pdf` 直接拉到 `paper_raw/wos_pdf/`；写盘前校验响应是 PDF。

Unpaywall 这条路径覆盖 Core Collection 的 OA 子集。被 Elsevier / Wiley / Springer 等付费墙挡住的记录会体现为 "no OA direct PDF"，留给用户自己走机构访问手动下载。

## 前置

- `paper_raw/_tmp/wos.txt` 已存在（见 `references/wos-delegation.md` §合并管道）
- Unpaywall 要求 query string 带邮箱；用当前用户的邮箱（见 `config.md` `{UNPAYWALL_EMAIL}`）
- 目标目录就绪：`./paper_raw/wos_pdf/`

## 管道

### Step A. 从 `wos.txt` 抽 DOI（及标签列）

按 `build_refs.py --wos` 的同一套方式解析（`DI` 取 DOI，`AU` 取第一作者，`PY` 取年份，`TI` 取题目）。走 high-quality 模式时，仅保留 ISSN 经 `journal_lookup` 映射到 CAS25 或 CAS26 1/2 区的记录。产出 tab 分隔的清单到 `paper_raw/_tmp/wos_dois.txt`：

```
<doi>\t<year>\t<first_author>\t<title>
```

### Step B–C. 扫 Unpaywall + 下载 OA PDF

运行权威脚本 `scripts/wos_oa_download.py`：

```bash
python scripts/wos_oa_download.py paper_raw/_tmp/wos_dois.txt paper_raw/wos_pdf
```

脚本做的事：
1. 对每行查 `api.unpaywall.org/v2/{doi}`（0.15 s 节流，符合 Unpaywall ~100 req/min 的指引），把 OA 子集写入 `paper_raw/_tmp/wos_oa_manifest.json`（带 `is_oa:true` 和 `best_oa_location.url_for_pdf`）。
2. 把每条 `url_for_pdf` 下载到 `<out_dir>/{Surname}_{Year}_{TitleAlphaNum}.pdf`（0.5 s 节流，校验 `%PDF` 头或 `pdf` Content-Type）。
3. 逐条打 OK/FAIL 行，末尾打 `oa_with_pdf / oa_no_pdf / no_oa / api_fail` 汇总。

邮箱参数：优先读 `PAPER_SEARCH_EMAIL` 环境变量（见 `config.md`）；未设置时脚本直接报错退出。把汇总行转述给用户，让用户看到 OA 命中率。

## 预期结果

- 主题类 CAS 1/2 区切片的典型命中率：过滤后的 WoS 集中 10–20% 会落到 `paper_raw/wos_pdf/`（一次实测 37/267 ≈ 14%）。
- Step C 常见报错是 HTTP 403（Wiley、Taylor & Francis 等出版商 CDN 的 bot 防护），计数后继续。
- 没有 OA PDF URL 的记录是合法终态——用户自行决定是否走机构访问手动拉。

## 已验证响应形态

| Unpaywall 字段 | 含义 | 动作 |
|---|---|---|
| `is_oa: true` + `best_oa_location.url_for_pdf: "https://..."` | 直连 PDF | 拉取 + 写盘 |
| `is_oa: true` + `url_for_pdf: null` | 仅 OA 落地页（摘要 / 出版商页面） | 跳过 |
| `is_oa: false` | 付费墙 | 跳过 |
| HTTP 404 on `/v2/{doi}` | Unpaywall 不认识该 DOI | 跳过 |

## 工具调用开销

零 chrome-devtools 调用。整条管道一次 `Bash` 调用 Python 脚本即可跑完。
