# paper-search

Claude Code skill for academic paper search, citation analysis, and metadata extraction across arXiv, Semantic Scholar, Google Scholar, PubMed, ACM DL, IEEE Xplore, Papers with Code, CNKI, and Web of Science. Produces a merged-deduplicated `refs.ris` plus a `summary.md` table per query.

## Acknowledgements

This project is a derivative work of **[ustc-ai4science/academic-search](https://github.com/ustc-ai4science/academic-search)** by **Chengmingyue**, originally released under the MIT License. The orchestration layout in `SKILL.md`, the per-source merge pipeline (`scripts/build_refs.py`), the CDP proxy (`scripts/cdp-proxy.mjs`), and most reference docs under `references/` are adapted from that upstream project and remain under its MIT license. See [`NOTICE`](NOTICE) for the full attribution and a summary of modifications, and [`LICENSE`](LICENSE) for the MIT terms covering both the upstream and the changes in this fork.

If you find this fork useful, please also star the upstream repository.

## Install

```bash
git clone https://github.com/<your-github>/paper-search ~/.claude/skills/paper-search
```

Then fill in `config.md` locally with your own keys/email/hosts (see the template inside — do not commit real values back).

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

> 搜一下 2024-2026 年 GraphRAG 的综述，arXiv + Semantic Scholar，最多 30 条

Output lands in `./paper_raw/` under the current working directory:

```
paper_raw/
├── refs.ris          # merged + deduped RIS (DOI > arXiv ID > WoS ID > title+year)
├── summary.md        # markdown table, newest-first
└── _tmp/             # per-source intermediates (can be deleted after merge)
```

See [`SKILL.md`](SKILL.md) for the full orchestration rules and [`references/`](references/) for per-database details.

## Differences from upstream

- Skill renamed `academic-search` → `paper-search`; env vars `ACADEMIC_SEARCH_*` → `PAPER_SEARCH_*`.
- `config.md` ships as a sanitized template (no embedded keys, email, or institutional VPN hosts).
- Added `LICENSE`, `NOTICE`, `README.md` for explicit MIT attribution.

## License

MIT — see [`LICENSE`](LICENSE). Retains the original copyright of **Chengmingyue (2026)** for the upstream work and adds **Tong Zhou (2026)** for modifications in this fork.
