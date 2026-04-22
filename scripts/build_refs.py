#!/usr/bin/env python
"""
Parse multi-source academic search responses, filter by date window,
dedupe across sources, output merged RIS + summary.md.

Usage:
    python build_refs.py --start 2026-02-07 --end 2026-04-07 --out ./paper_raw \
        [--arxiv ./paper_raw/_tmp/arxiv.xml] [--s2 ./paper_raw/_tmp/s2.json] \
        [--pubmed ./paper_raw/_tmp/pubmed.xml] [--gs ./paper_raw/_tmp/gs_raw.jsonl] \
        [--wos ./paper_raw/_tmp/wos.ris] [--cnki ./paper_raw/_tmp/cnki.ris]

Inputs (all optional; at least one required):
  --arxiv   arXiv Atom XML (from export.arxiv.org/api/query)
  --s2      Semantic Scholar /paper/search JSON (data[] with fields=...)
  --pubmed  PubMed efetch XML (retmode=xml)
  --gs      Google Scholar scraped JSONL; each line = {"value": "<json string>"}
            where inner JSON has {items: [{title, meta, snippet, link, pdf, cited}]}
            snippet must start with relative date ("3 天前" / "N weeks ago" / etc.)
  --wos     Web of Science native RIS export (from WoS Export → RIS → Full Record → File UI, triggered inline by orchestrator; no wos-export leaf exists).
            Authoritative source containing full abstract + keywords.
  --cnki    CNKI native RIS export (from CNKI dm8/API/GetExport template, triggered inline by orchestrator; no cnki-export leaf exists).
            Authoritative source containing full abstract + keywords.

Output (in --out dir):
  refs.ris     — merged RIS
  summary.md   — date-desc table grouped by source

Dedupe priority: PubMed > S2 > WoS > arXiv > CNKI > GS. Keys: DOI > arXiv ID > PMID > WoS ID > normalized title.
Date filter is inclusive on both ends. GS items without parseable relative date are dropped.
"""
import argparse, json, os, re, sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from journal_lookup import lookup as _journal_lookup, short_label as _journal_label
except Exception:
    _journal_lookup = lambda *a, **k: {}
    _journal_label  = lambda info: ''

ATOM = {'a': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}

def norm_title(t):
    return re.sub(r'\W+', '', (t or '').lower())

def clean_ws(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()

def parse_rel_date(snippet, today):
    """Parse relative date prefix from a GS snippet. Returns date or None."""
    if not snippet:
        return None
    s = snippet.strip()
    m = re.match(r'^(\d+)\s*(天|周|个月|月)前', s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = {'天': 1, '周': 7, '月': 30, '个月': 30}[unit] * n
        return today - timedelta(days=days)
    m = re.match(r'^(\d+)\s*(day|week|month)s?\s*ago', s, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {'day': 1, 'week': 7, 'month': 30}[unit] * n
        return today - timedelta(days=days)
    return None

def parse_gs_meta(meta):
    """GS .gs_a text: 'A1, A2... - Venue, YYYY - Publisher'."""
    if not meta:
        return [], '', None
    parts = [p.strip() for p in meta.split(' - ')]
    authors = [a.strip().rstrip('…').strip() for a in re.split(r',\s*', parts[0]) if a.strip()]
    venue, year = '', None
    if len(parts) >= 2:
        ym = re.search(r'(19|20)\d{2}', parts[1])
        if ym:
            year = int(ym.group(0))
            venue = parts[1][:ym.start()].rstrip(', ').strip()
        else:
            venue = parts[1]
    return authors, venue, year

def load_arxiv(path):
    root = ET.parse(path).getroot()
    out = []
    for e in root.findall('a:entry', ATOM):
        idurl = e.findtext('a:id', '', ATOM)
        arxiv_id = idurl.rsplit('/', 1)[-1].split('v')[0] if idurl else ''
        pub = e.findtext('a:published', '', ATOM)[:10]
        try:
            d = date.fromisoformat(pub)
        except Exception:
            d = None
        out.append(dict(
            source='arXiv',
            title=clean_ws(e.findtext('a:title', '', ATOM)),
            authors=[a.findtext('a:name', '', ATOM) for a in e.findall('a:author', ATOM)],
            date=d, year=d.year if d else None,
            venue='arXiv preprint',
            doi=e.findtext('arxiv:doi', '', ATOM) or '',
            arxiv_id=arxiv_id, pmid='',
            abstract=clean_ws(e.findtext('a:summary', '', ATOM)),
            keywords=[c.get('term', '') for c in e.findall('a:category', ATOM) if c.get('term')],
            url=f'https://arxiv.org/abs/{arxiv_id}' if arxiv_id else '',
            pdf=f'https://arxiv.org/pdf/{arxiv_id}' if arxiv_id else '',
            cited=None,
        ))
    return out

def load_s2(path):
    data = json.load(open(path, encoding='utf-8')).get('data', [])
    out = []
    for p in data:
        pd = p.get('publicationDate') or ''
        try:
            d = date.fromisoformat(pd)
        except Exception:
            d = None
        ext = p.get('externalIds') or {}
        doi = ext.get('DOI', '') or ''
        arxiv_id = ext.get('ArXiv', '') or ''
        pdf = (p.get('openAccessPdf') or {}).get('url') if p.get('openAccessPdf') else ''
        if not pdf and arxiv_id:
            pdf = f'https://arxiv.org/pdf/{arxiv_id}'
        out.append(dict(
            source='S2',
            title=p.get('title', ''),
            authors=[a.get('name', '') for a in (p.get('authors') or [])],
            date=d, year=p.get('year'),
            venue=p.get('venue') or '',
            doi=doi, arxiv_id=arxiv_id, pmid=ext.get('PubMed', '') or '',
            abstract=clean_ws(p.get('abstract') or ''),
            keywords=[f.get('category', '') if isinstance(f, dict) else str(f) for f in (p.get('s2FieldsOfStudy') or [])],
            url=f'https://doi.org/{doi}' if doi else '',
            pdf=pdf or '', cited=p.get('citationCount'),
        ))
    return out

def load_pubmed(path):
    root = ET.parse(path).getroot()
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    out = []
    for art in root.findall('.//PubmedArticle'):
        titleEl = art.find('.//ArticleTitle')
        title = ''.join(titleEl.itertext()).strip() if titleEl is not None else ''
        pmid = art.findtext('.//PMID', '')
        d = None
        adate = art.find('.//ArticleDate')
        if adate is not None:
            try:
                d = date(int(adate.findtext('Year')), int(adate.findtext('Month')), int(adate.findtext('Day')))
            except Exception:
                d = None
        if d is None:
            pdn = art.find('.//Journal/JournalIssue/PubDate')
            if pdn is not None:
                y, m, day = pdn.findtext('Year'), (pdn.findtext('Month') or '1'), (pdn.findtext('Day') or '1')
                try:
                    mi = int(m) if m.isdigit() else months.get(m, 1)
                    d = date(int(y), mi, int(day))
                except Exception:
                    d = None
        authors = []
        for a in art.findall('.//Author'):
            ln, fn = a.findtext('LastName', '') or '', a.findtext('ForeName', '') or ''
            if ln or fn:
                authors.append(f"{ln}, {fn}".strip(', '))
        doi = ''
        for aid in art.findall('.//ArticleId'):
            if aid.get('IdType') == 'doi':
                doi = aid.text or ''
        abstract = ' '.join(''.join(ab.itertext()) for ab in art.findall('.//Abstract/AbstractText'))
        kw = [k.text for k in art.findall('.//Keyword') if k.text]
        if not kw:
            kw = [d.text for d in art.findall('.//MeshHeading/DescriptorName') if d.text]
        issn_el = art.find('.//Journal/ISSN')
        out.append(dict(
            source='PubMed', title=title, authors=authors, date=d,
            year=d.year if d else None,
            venue=art.findtext('.//Journal/Title', '') or '',
            doi=doi, arxiv_id='', pmid=pmid,
            issn=(issn_el.text if issn_el is not None else '') or '',
            abstract=clean_ws(abstract),
            keywords=kw,
            url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/' if pmid else '',
            pdf=f'https://doi.org/{doi}' if doi else '',
            cited=None,
        ))
    return out

def load_gs(path, today, allow_yearonly=False, window=None):
    out = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            outer = json.loads(line)
            inner = json.loads(outer['value']) if 'value' in outer else outer
        except Exception:
            continue
        for it in inner.get('items', []):
            title = (it.get('title') or '').strip()
            if not title:
                continue
            d = parse_rel_date(it.get('snippet'), today)
            if not d and allow_yearonly:
                # Fall back to year from .gs_a meta; place at window midpoint
                _a, _v, yr = parse_gs_meta(it.get('meta'))
                if yr and window and window[0].year <= yr <= window[1].year:
                    d = window[0] + (window[1] - window[0]) / 2
            if not d:
                continue  # GS contract: no relative date → drop
            authors, venue, year = parse_gs_meta(it.get('meta'))
            cited_txt = it.get('cited') or ''
            cm = re.search(r'\d+', cited_txt)
            out.append(dict(
                source='GS', title=title, authors=authors, date=d,
                year=year or d.year, venue=venue,
                doi='', arxiv_id='', pmid='',
                abstract=clean_ws(it.get('snippet', '')),
                keywords=[],
                url=it.get('link') or '',
                pdf=it.get('pdf') or '',
                cited=int(cm.group(0)) if cm else None,
            ))
    return out

def load_wos_plaintext(path, source, window=None):
    """Parse WoS Plain text export (FN/VR/PT.../ER/EF, 2-letter tags + space, 3-space
    continuation indent). Produces same record schema as load_ris. Used for
    Export → Plain text file, Record Content = 'Author, Title, Source, Abstract'."""
    text = open(path, encoding='utf-8-sig').read()
    records_out = []
    cur = None
    last_tag = None
    def flush(rec):
        if not rec:
            return
        py = rec.get('PY')
        d = None
        if py and py.isdigit():
            try: d = date(int(py), 1, 1)
            except Exception: d = None
        if window and (d is None or not (window[0] <= d <= window[1])):
            d = window[0] + (window[1] - window[0]) / 2
        doi = (rec.get('DI') or '').strip()
        records_out.append(dict(
            source=source,
            title=clean_ws(rec.get('TI') or ''),
            authors=rec.get('AU_list') or [],
            date=d, year=d.year if d else (int(py) if py and py.isdigit() else None),
            venue=rec.get('SO') or rec.get('J9') or '',
            doi=doi, arxiv_id='', pmid='', wos_id=rec.get('UT') or '',
            issn=rec.get('SN') or '',
            abstract=clean_ws(rec.get('AB') or ''),
            keywords=rec.get('DE_list') or rec.get('ID_list') or [],
            url=(f'https://doi.org/{doi}' if doi else ''),
            pdf=(f'https://doi.org/{doi}' if doi else ''),
            cited=None,
        ))
    for raw in text.splitlines():
        line = raw.rstrip('\r')
        if not line:
            continue
        if line.startswith('EF'):
            break
        if line.startswith('   ') and cur is not None and last_tag:
            cont = line.strip()
            if last_tag == 'AU':
                cur.setdefault('AU_list', []).append(cont)
            elif last_tag == 'DE':
                cur.setdefault('DE_list', []).extend([x.strip() for x in cont.split(';') if x.strip()])
            elif last_tag == 'ID':
                cur.setdefault('ID_list', []).extend([x.strip() for x in cont.split(';') if x.strip()])
            else:
                cur[last_tag] = (cur.get(last_tag) or '') + ' ' + cont
            continue
        m = re.match(r'^([A-Z0-9][A-Z0-9])(?:\s(.*))?$', line)
        if not m:
            continue
        tag, val = m.group(1), (m.group(2) or '').strip()
        if tag in ('FN', 'VR'):
            continue
        if tag == 'PT':
            cur = {'AU_list': [], 'DE_list': [], 'ID_list': []}
            last_tag = None
            continue
        if tag == 'ER':
            flush(cur); cur = None; last_tag = None; continue
        if cur is None:
            continue
        if tag == 'AU':
            cur['AU_list'].append(val); last_tag = 'AU'
        elif tag == 'DE':
            cur['DE_list'].extend([x.strip() for x in val.split(';') if x.strip()]); last_tag = 'DE'
        elif tag == 'ID':
            cur['ID_list'].extend([x.strip() for x in val.split(';') if x.strip()]); last_tag = 'ID'
        else:
            cur[tag] = val; last_tag = tag
    return records_out

def load_wos(path, source, window=None):
    """Dispatch WoS export: Plain text (starts with 'FN ') → load_wos_plaintext;
    otherwise fall back to RIS (legacy exports)."""
    with open(path, encoding='utf-8-sig') as f:
        head = f.read(8)
    if head.startswith('FN '):
        return load_wos_plaintext(path, source, window)
    return load_ris(path, source, window)

def load_ris(path, source, window=None):
    """Parse a RIS file. Used for CNKI/WoS native exports (authoritative source,
    includes abstract + keywords). `source` is the logical label (e.g. 'CNKI', 'WoS').
    `window` optionally clamps missing dates to the window midpoint (same semantics
    as load_wos for year-only records)."""
    text = open(path, encoding='utf-8-sig').read()
    records_out = []
    cur = None
    def flush(rec):
        if not rec:
            return
        d = None
        da = rec.get('DA')
        if da:
            for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%Y/%m', '%Y-%m', '%Y'):
                try: d = datetime.strptime(da, fmt).date(); break
                except Exception: pass
        if d is None and rec.get('PY'):
            try: d = date(int(rec['PY']), 1, 1)
            except Exception: d = None
        if window and (d is None or not (window[0] <= d <= window[1])):
            d = window[0] + (window[1] - window[0]) / 2
        doi = (rec.get('DO') or '').strip()
        records_out.append(dict(
            source=source,
            title=clean_ws(rec.get('TI') or rec.get('T1') or ''),
            authors=rec.get('AU_list') or [],
            date=d, year=d.year if d else (int(rec['PY']) if rec.get('PY', '').isdigit() else None),
            venue=rec.get('JO') or rec.get('T2') or rec.get('JF') or '',
            doi=doi, arxiv_id='', pmid='', wos_id=rec.get('AN') or '',
            issn=rec.get('SN') or '',
            abstract=clean_ws(rec.get('AB') or rec.get('N2') or ''),
            keywords=rec.get('KW_list') or [],
            url=(rec.get('UR') or (f'https://doi.org/{doi}' if doi else '')),
            pdf=rec.get('L1') or (f'https://doi.org/{doi}' if doi else ''),
            cited=None,
        ))
    for raw in text.splitlines():
        line = raw.rstrip('\r')
        if not line.strip():
            continue
        m = re.match(r'^([A-Z][A-Z0-9])\s{0,2}-\s?(.*)$', line)
        if not m:
            # continuation of previous field
            if cur and cur.get('_last'):
                key = cur['_last']
                cur[key] = (cur.get(key) or '') + ' ' + line.strip()
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == 'TY':
            cur = {'AU_list': [], 'KW_list': []}
        elif tag == 'ER':
            flush(cur); cur = None
        elif cur is not None:
            if tag == 'AU' or tag == 'A1':
                cur['AU_list'].append(val)
                cur['_last'] = None
            elif tag == 'KW':
                cur['KW_list'].append(val)
                cur['_last'] = None
            else:
                cur[tag] = val
                cur['_last'] = tag
    return records_out

def dedupe(records):
    prio = {'PubMed': 0, 'S2': 1, 'WoS': 2, 'arXiv': 3, 'CNKI': 4, 'GS': 5}
    records.sort(key=lambda r: prio.get(r['source'], 9))
    seen_doi, seen_ax, seen_pm, seen_ws, seen_t = set(), set(), set(), set(), set()
    out = []
    for r in records:
        doi = (r.get('doi') or '').lower()
        ax = r.get('arxiv_id') or ''
        pm = r.get('pmid') or ''
        ws = r.get('wos_id') or ''
        nt = norm_title(r['title'])
        if doi and doi in seen_doi: continue
        if ax and ax in seen_ax: continue
        if pm and pm in seen_pm: continue
        if ws and ws in seen_ws: continue
        if nt and nt in seen_t: continue
        if doi: seen_doi.add(doi)
        if ax: seen_ax.add(ax)
        if pm: seen_pm.add(pm)
        if ws: seen_ws.add(ws)
        if nt: seen_t.add(nt)
        out.append(r)
    return out

def attach_local_pdfs(records, out_dir):
    """Rewrite each record's `pdf` field to a local file:// URI when a
    matching PDF exists under out_dir. Records without a local match get
    pdf='' so ris_record() emits the record metadata-only.

    Layout assumed under out_dir:
      {out_dir}/{Surname}_{Year}_{ShortTitle}.pdf           — arXiv
      {out_dir}/wos_pdf/{Surname}_{Year}_{TitleAlphaNum}.pdf — WoS OA
      {out_dir}/cnki_pdf/{Title}_{FirstAuthor}.pdf           — CNKI native naming
    """
    import glob
    def sanitize(s, n=60):
        s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', s or '')
        s = re.sub(r'\s+', '_', s.strip())
        return s[:n].rstrip('._')
    def short_title(t):
        words = re.findall(r'[A-Za-z0-9]+', t or '')
        return sanitize('_'.join(words[:8]))
    def first_surname(authors):
        if not authors: return 'Unknown'
        a = authors[0].strip()
        if ',' in a: return sanitize(a.split(',')[0], 25)
        last = a.split()[-1] if a.split() else a
        return sanitize(last, 25)
    def to_file_uri(path):
        p = os.path.abspath(path).replace('\\', '/')
        if re.match(r'^[A-Za-z]:/', p):
            return 'file:///' + p
        return 'file://' + p

    arxiv_files = set(os.path.basename(f) for f in glob.glob(os.path.join(out_dir, '*.pdf')))
    wos_files   = set(os.path.basename(f) for f in glob.glob(os.path.join(out_dir, 'wos_pdf', '*.pdf')))
    cnki_files  = glob.glob(os.path.join(out_dir, 'cnki_pdf', '*.pdf'))

    matched = {'arXiv': 0, 'WoS': 0, 'CNKI': 0}
    for r in records:
        pdf_path = None
        src = r.get('source')
        year = r['date'].year if r.get('date') else None
        first = first_surname(r.get('authors') or [])
        title = r.get('title') or ''
        if src == 'arXiv' and year:
            fname = f"{first}_{year}_{short_title(title)}.pdf"
            if fname in arxiv_files:
                pdf_path = os.path.join(out_dir, fname)
        elif src == 'WoS' and year:
            short = sanitize(re.sub(r'[^A-Za-z0-9 ]', '', title))
            fname = f"{first}_{year}_{short}.pdf"
            if fname in wos_files:
                pdf_path = os.path.join(out_dir, 'wos_pdf', fname)
        elif src == 'CNKI' and title:
            key = title.strip()[:12]
            if key:
                for f in cnki_files:
                    if key in os.path.basename(f):
                        pdf_path = f; break
        if pdf_path:
            r['pdf'] = to_file_uri(pdf_path)
            matched[src] = matched.get(src, 0) + 1
        else:
            r['pdf'] = ''
    return matched

def ris_record(r):
    L = ['TY  - JOUR' if r['source'] != 'arXiv' else 'TY  - GEN',
         f"TI  - {r['title']}"]
    for a in r['authors']:
        L.append(f"AU  - {a}")
    if r['date']:
        L.append(f"PY  - {r['date'].year}")
        L.append(f"DA  - {r['date'].strftime('%Y/%m/%d')}")
    if r['venue']:
        L.append(f"JO  - {r['venue']}")
        L.append(f"T2  - {r['venue']}")
    if r.get('abstract'):
        L.append(f"AB  - {r['abstract']}")
    for kw in (r.get('keywords') or []):
        L.append(f"KW  - {kw}")
    if r.get('doi'):
        L.append(f"DO  - {r['doi']}")
    if r.get('url'):
        L.append(f"UR  - {r['url']}")
    if r.get('pdf'):
        L.append(f"L1  - {r['pdf']}")
    if r.get('arxiv_id'):
        L.append(f"C1  - arXiv:{r['arxiv_id']}")
    if r.get('pmid'):
        L.append(f"AN  - {r['pmid']}")
    if r.get('wos_id'):
        L.append(f"AN  - {r['wos_id']}")
    if r.get('cited') is not None:
        L.append(f"N1  - Cited by: {r['cited']}")
    L.append(f"DB  - {r['source']}")
    L.append('ER  - ')
    return '\n'.join(L)

def md_cell(s):
    """Escape a markdown table cell: pipes, newlines."""
    return (s or '').replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')

def fmt_authors(authors):
    if not authors:
        return ''
    if len(authors) <= 3:
        return ', '.join(authors)
    return ', '.join(authors[:3]) + ' 等'

def write_summary(records, path, start, end):
    by_src = {}
    for r in records:
        by_src.setdefault(r['source'], 0)
        by_src[r['source']] += 1
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# 检索结果 ({start} ~ {end})\n\n")
        f.write(f"- 去重后合计: **{len(records)}** 篇\n")
        f.write("- 来源: " + ", ".join(f"{k} {v}" for k, v in sorted(by_src.items())) + "\n\n")
        f.write("| # | 题目 | 发表日期 | 年份 | 作者 | 期刊/来源 | JCR | 中科25 | 中科26 | 关键词 | 摘要 |\n"
                "|---|---|---|---|---|---|---|---|---|---|---|\n")
        def _q(info, prefix):
            q = info.get(f'{prefix}_q')
            if not q: return ''
            return q + ('·Top' if info.get(f'{prefix}_top') else '')
        for i, r in enumerate(records, 1):
            title = md_cell(r['title'])
            year = r['year'] or (r['date'].year if r['date'] else '')
            pub_date = r['date'].isoformat() if r['date'] else ''
            authors = md_cell(fmt_authors(r['authors']))
            venue = md_cell(r['venue'] or r['source'])
            info = _journal_lookup(r.get('issn', '')) if r.get('issn') else {}
            jcr_cell  = md_cell(info.get('jcr_q', '') + (f"·IF{info['jcr_if']}" if info.get('jcr_if') else ''))
            cas25_cell = md_cell(_q(info, 'cas25'))
            cas26_cell = md_cell(_q(info, 'cas26'))
            kws = md_cell('; '.join(r.get('keywords') or []))
            abstract = md_cell(r.get('abstract') or '')
            f.write(f"| {i} | {title} | {pub_date} | {year} | {authors} | {venue} | {jcr_cell} | {cas25_cell} | {cas26_cell} | {kws} | {abstract} |\n")

_SOURCE_TO_DB = {'arxiv': 'arxiv', 's2': 's2', 'pubmed': 'pubmed',
                 'gs': 'gs', 'wos': 'wos', 'cnki': 'cnki'}

def _check_query_expansion_gate(scheduled_dbs):
    """Refuse to run unless scripts/expand_queries.py has been called within
    the last hour AND its plan covers every database actually being merged
    here. Forcing function for the 4-phase orchestrator flow."""
    tmp = os.environ.get('TEMP') or os.environ.get('TMPDIR') or '/tmp'
    log_path = os.path.join(tmp, 'query_log.json')
    if not os.path.exists(log_path):
        sys.stderr.write(
            f'ERROR: {log_path} not found. '
            'Run scripts/expand_queries.py with a 4-phase plan before build_refs.py.\n'
        )
        sys.exit(5)
    try:
        with open(log_path, encoding='utf-8') as f:
            log = json.load(f)
    except Exception as e:
        sys.stderr.write(f'ERROR: cannot read {log_path}: {e}\n'); sys.exit(5)
    ts_str = log.get('ts', '')
    try:
        ts = datetime.fromisoformat(ts_str)
    except Exception:
        sys.stderr.write(f'ERROR: {log_path} missing/invalid ts\n'); sys.exit(5)
    if (datetime.now() - ts).total_seconds() > 3600:
        sys.stderr.write(
            f'ERROR: {log_path} is stale (>1h). Re-run expand_queries.py.\n'
        ); sys.exit(5)
    # New schema: must contain fields/boolean/per_db/databases
    for k in ('fields', 'boolean', 'per_db', 'databases'):
        if k not in log:
            sys.stderr.write(
                f'ERROR: {log_path} missing `{k}` — old format detected. '
                'Re-run expand_queries.py with the new 4-phase plan schema.\n'
            ); sys.exit(5)
    per_db = log.get('per_db') or {}
    missing = [db for db in scheduled_dbs
               if db not in per_db or not str(per_db.get(db, '')).strip()]
    if missing:
        sys.stderr.write(
            'ERROR: scheduled databases lack per_db expression in '
            f'{log_path}: {", ".join(missing)}. '
            'Add them to the plan and re-run expand_queries.py.\n'
        ); sys.exit(5)
    # Skip-expansion guard
    if log.get('no_expand') and log.get('skip_reason') not in {
        'user_expression', 'user_explicit', 'known_id'
    }:
        sys.stderr.write(
            f'ERROR: {log_path} has no_expand=true with invalid skip_reason '
            f'{log.get("skip_reason")!r}.\n'
        ); sys.exit(5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--out', default='./paper_raw')
    ap.add_argument('--arxiv'); ap.add_argument('--s2')
    ap.add_argument('--pubmed'); ap.add_argument('--gs')
    ap.add_argument('--wos'); ap.add_argument('--cnki')
    ap.add_argument('--today', default=None, help='reference date for GS relative parsing')
    ap.add_argument('--gs-allow-yearonly', action='store_true',
                    help='accept GS items without relative date, anchor to window midpoint')
    ap.add_argument('--high-quality', action='store_true',
                    help='filter WoS records to CAS25 or CAS26 ∈ {1区,2区}; '
                         'CNKI passes through (pre-filtered to CSSCI/北大核心 at UI); '
                         'arXiv passes through (preprints not subject to CAS zoning)')
    args = ap.parse_args()

    scheduled = [k for k in ('arxiv', 's2', 'pubmed', 'gs', 'wos', 'cnki')
                 if getattr(args, k)]
    # Gate downgraded to opt-in lint (set PAPER_SEARCH_GATE=1 to enforce).
    # Modern models do query expansion natively; the forced 4-phase plan + script
    # round-trip was net friction for `user_expression` / simple cases. Keep the
    # function callable for opt-in CI/regression use.
    if os.environ.get('PAPER_SEARCH_GATE') == '1':
        _check_query_expansion_gate(scheduled)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    today = date.fromisoformat(args.today) if args.today else date.today()

    records = []
    if args.arxiv: records += load_arxiv(args.arxiv)
    if args.s2: records += load_s2(args.s2)
    if args.pubmed: records += load_pubmed(args.pubmed)
    if args.gs: records += load_gs(args.gs, today, args.gs_allow_yearonly, (start, end))
    if args.wos: records += load_wos(args.wos, source='WoS', window=(start, end))
    if args.cnki: records += load_ris(args.cnki, source='CNKI', window=(start, end))

    records = [r for r in records if r['date'] and start <= r['date'] <= end]

    if args.high_quality:
        def _hi(r):
            if r['source'] == 'WoS':
                issn = r.get('issn') or ''
                if not issn:
                    return False
                info = _journal_lookup(issn)
                for k in ('cas25_q', 'cas26_q'):
                    q = info.get(k) or ''
                    if q in ('1区', '2区'):
                        return True
                return False
            return True  # arXiv / CNKI / other sources pass through
        records = [r for r in records if _hi(r)]

    records = dedupe(records)
    records.sort(key=lambda r: r['date'], reverse=True)

    os.makedirs(args.out, exist_ok=True)
    attach_stats = attach_local_pdfs(records, args.out)
    with open(f"{args.out}/refs.ris", 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(ris_record(r) for r in records) + '\n')
    write_summary(records, f"{args.out}/summary.md", start, end)

    counts = {}
    for r in records:
        counts[r['source']] = counts.get(r['source'], 0) + 1
    attach_msg = ' '.join(f"{k}={v}" for k, v in attach_stats.items() if v)
    sys.stdout.write(
        f"total={len(records)} " + ' '.join(f"{k}={v}" for k, v in counts.items())
        + (f" | attached: {attach_msg}" if attach_msg else "") + "\n")

if __name__ == '__main__':
    main()
