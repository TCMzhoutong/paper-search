<p align="right">🌐 <a href="README.zh-CN.md">简体中文</a> | English</p>

# paper-search

Claude Code skill for academic paper search, citation analysis, and metadata extraction across **arXiv, Semantic Scholar, Google Scholar, PubMed, ACM DL, IEEE Xplore, Papers with Code, CNKI, and Web of Science**. Produces a cross-source deduplicated `refs.ris` plus a `summary.md` table per query.

## Acknowledgements

This project is a derivative work of **[ustc-ai4science/academic-search](https://github.com/ustc-ai4science/academic-search)** by **Chengmingyue**, originally released under the MIT License. The baseline orchestration shape in `SKILL.md`, the CDP proxy (`scripts/cdp-proxy.mjs`), the API cookbook (`references/api-cookbook.md`), and the site-pattern notes for arXiv / Semantic Scholar / Google Scholar / PubMed / ACM DL / IEEE / Papers with Code are adapted from that upstream project and remain under its MIT license.

See [`NOTICE`](NOTICE) for a file-level attribution breakdown, and [`LICENSE`](LICENSE) for the MIT terms covering both the upstream and the additions in this fork.

If you find this fork useful, please also star the upstream repository.

## Install

```bash
git clone https://github.com/TCMzhoutong/paper-search ~/.claude/skills/paper-search
```

Then fill in `config.md` locally with your own keys / email / hosts (see the template inside — do not commit real values back).

Required / optional accounts:
- **Semantic Scholar API key** (optional but recommended for higher rate limits) — https://www.semanticscholar.org/product/api
- **Unpaywall email** (required for open-access PDF lookups via `scripts/wos_oa_download.py`)
- **CNKI / Web of Science access** (institutional IP allow-list or VPN reverse-proxy, only needed if you query those sources)

Environment variables:

```bash
export S2_API_KEY="<your-s2-api-key>"
export PAPER_SEARCH_EMAIL="<your-email@example.com>"
```

## Usage

Invoke from Claude Code with any search-intent phrase the skill's frontmatter lists (Chinese or English). Typical one-shot:

> Search the last two years of GraphRAG surveys on arXiv + Semantic Scholar, max 30 hits

Output lands in `./paper_raw/` under the current working directory:

```
paper_raw/
├── refs.ris          # merged + deduped RIS (DOI > arXiv ID > WoS ID > title+year)
├── summary.md        # markdown table, newest-first
└── _tmp/             # per-source intermediates (can be deleted after merge)
```

See [`SKILL.md`](SKILL.md) for the full orchestration rules and [`references/`](references/) for per-database details.

## Differences from upstream

This section lists every change against [`ustc-ai4science/academic-search`](https://github.com/ustc-ai4science/academic-search) (baseline: commit `df71ccc`). A file-level attribution breakdown lives in [`NOTICE`](NOTICE).

### 1. Rename and attribution

- Skill renamed `academic-search` → `paper-search`; `SKILL.md` frontmatter `name`, `version` bumped to `2.0.0`.
- Environment variables renamed: `ACADEMIC_SEARCH_EMAIL` → `PAPER_SEARCH_EMAIL`, `ACADEMIC_SEARCH_GATE` → `PAPER_SEARCH_GATE`.
- `LICENSE` updated to a dual-copyright MIT (Chengmingyue 2026 + Tong Zhou 2026).
- New `NOTICE` file with file-level attribution.
- New `README.md` + `README.zh-CN.md` written from scratch (replacing upstream's marketing-style READMEs).

### 2. Deliverable contract

Upstream instructs the model to emit a per-platform RIS/JSON/Markdown in free form. This fork pins down a **three-file contract** that every search task must produce, under `./paper_raw/` in the current working directory:

```
paper_raw/
├── refs.ris          # cross-source merged & deduped
├── summary.md        # newest-first markdown table, fixed column set
├── _tmp/             # per-source intermediates (arxiv.xml / s2.json / cnki.ris / wos.txt / ...)
└── {Author}_{Year}_{Title}.pdf × N   # only when the user explicitly asks to download
```

`summary.md` has a fixed column set: `题目 | 发表日期 | 年份 | 作者 | 期刊/来源 | JCR | 中科25 | 中科26 | 关键词 | 摘要`, with `发表日期` as ISO `YYYY-MM-DD` (falls back to `YYYY-01-01` when the source only provides a year).

### 3. New cross-source merger — `scripts/build_refs.py` (~664 lines)

Reads every `paper_raw/_tmp/{arxiv.xml, s2.json, pubmed.xml, pwc.json, cnki.ris, wos.txt, ...}`, cross-source dedupes in the priority order **DOI > arXiv ID > WoS ID > title+year fuzzy match**, writes the final `refs.ris` (with `DO` for any source that has a DOI and `L1` linking to the local PDF when one was downloaded), and materialises `summary.md`.

### 4. Structured query plan — `references/query-plan.md` + `scripts/expand_queries.py` (~249 lines)

A four-phase plan (intent → concept decomposition → per-DB expression synthesis → execution scheduling) with an optional JSON schema. `scripts/expand_queries.py` validates a plan and can be enforced by setting `PAPER_SEARCH_GATE=1` before `build_refs.py` runs. Includes a per-DB syntax cheat-sheet (arXiv `ti:`+`abs:` + `submittedDate:`, S2 `query`, PubMed `[Title/Abstract]` + `datetype=pdat`, WoS `TS=`, CNKI `TKA=`, Google Scholar nested boolean).

### 5. Database selection hardened

- **Hard rule**: when the user names specific databases, only those databases run; no fallback to other sources when one fails.
- New "default parallel" vs "on-demand join" matrix: arXiv + Semantic Scholar are the default parallel pair; PubMed / Papers with Code / ACM DL / IEEE / GS / CNKI / WoS join only when the intent signals match.
- **Browser-driven databases (CNKI, WoS, GS) run strictly serial**, because chrome-devtools MCP maintains a single global "current page" state. Parallelising them corrupts cookies and VPN sessions. `references/parallel.md` documents this and the API-side parallel pattern.

### 6. CNKI pipeline (new, ~356 lines)

Upstream only had a short site-pattern note for `cnki.net`. This fork replaces it with:

- `references/cnki-advanced-search.md` — CNKI professional expression language spec (`TKA=` field code, `+` / `*` / `%` operators, academic-Chinese term translation table).
- `references/cnki-delegation.md` — delegation contract and the `dm8/API/GetExport` JS template that turns a result page into a RIS blob, saved as `paper_raw/_tmp/cnki.ris`.
- `references/cnki-download.md` — per-record PDF download UI sequence.
- Institutional VPN reverse-proxy host handling in `config.md` (template only — fill your own).

### 7. Web of Science pipeline (new, ~107 lines)

Upstream has no WoS support at all. This fork adds:

- `references/wos-delegation.md` — VPN routing rules, advanced-search flow, `TS=` expression syntax, session recovery after dead-node 503s.
- `references/wos-download.md` — `Export → Plain text file` export, Unpaywall-based open-access PDF lookup flow.
- `scripts/wos_oa_download.py` (~95 lines) — per-DOI Unpaywall query and OA PDF download.

### 8. Journal-quality metadata — `data/jcr.db` + `scripts/journal_lookup.py`

16 MB SQLite database of Journal Citation Report metadata. `scripts/journal_lookup.py` (~141 lines) returns JCR quartile, CAS zone (中科院分区, both 2025 and 2026 editions), and impact factor for a journal name or ISSN. `build_refs.py` calls it while materialising `summary.md`.

### 9. arXiv batch downloader — `scripts/download_arxiv.py` (~79 lines)

Parses the Atom XML returned by arXiv and downloads each paper as `{FirstAuthorSurname}_{Year}_{ShortTitle}.pdf`, respecting the 3 s per-request throttle. Only triggered when the user explicitly says "下载" / "download".

### 10. Personal configuration single-source-of-truth — `config.md`

Upstream hard-codes no keys but also provides no coherent place to put them. This fork adds a single `config.md` template that documents every placeholder (`{S2_API_KEY}` / `{UNPAYWALL_EMAIL}` / `{CNKI_HOST}` / `{WOS_HOST}`) plus the matching env var (`S2_API_KEY`, `PAPER_SEARCH_EMAIL`). The file ships sanitised — no real keys / email / institutional VPN hosts committed. `.gitignore` has been extended to keep `config.local.md` / `.env*` / `paper_raw/` out of the repo.

### 11. `SKILL.md` rewritten as a pure orchestration layer

Upstream `SKILL.md` is ~323 lines with a large "search philosophy" preamble (success criteria, two-pass scanning, failure-signal tables). This fork compresses it to ~173 lines by:

- Removing the preflight `check-deps.sh` section.
- Replacing the platform table with the default-parallel / on-demand-join matrix described above.
- Delegating all CNKI / WoS / GS work to the corresponding reference docs (inline `chrome-devtools` MCP execution, no sub-agent wrapping).
- Pinning the `paper_raw/_tmp/` intermediate-file path explicitly.
- Adding a "hard rules" section (enumerations are not extensible, browser databases are strictly serial, `Skill(cnki-advanced-search)` is not a registered skill — reference docs are read and executed inline).

### 12. Site-pattern extensions

- `references/site-patterns/arxiv.org.md` — appended 2026-04-07 observations on Varnish 429/503 cooldowns (60–90 s, cannot be shortened by retrying), and stricter `submittedDate:[...]` range recommendation.
- `references/site-patterns/scholar.google.com.md` — appended a "search expression construction" section (unbounded nested booleans, no field prefixes, phrase quoting) with a multi-concept example, and a stricter "time filter" section describing the lack of reliable publication-month metadata.

### 13. Upstream files not carried over

`Makefile`, `agents/openai.yaml`, `assets/*`, `docs/skill-usage-comparison.md`, `wechat-promo.md`, `scripts/check-deps.sh`, `scripts/release-test.sh`, `scripts/self-test.sh`, `references/metadata-schema.md`, `references/venue-rankings.md`, `references/site-patterns/cnki.net.md`, `README.en.md`. See `NOTICE` for rationale.

## License

MIT — see [`LICENSE`](LICENSE). Retains the original copyright of **Chengmingyue (2026)** for the upstream work and adds **Tong Zhou (2026)** for modifications in this fork.
