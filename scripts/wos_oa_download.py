#!/usr/bin/env python
"""Scan DOIs via Unpaywall and download OA PDFs that carry a direct url_for_pdf.

Usage:
    python wos_oa_download.py <dois_tsv> [out_dir] [email]

Arguments:
    dois_tsv   Tab-separated manifest: <doi>\\t<year>\\t<first_author>\\t<title>
               (produced by extracting from a WoS Plain text export; see references/wos-download.md)
    out_dir    Destination folder for PDFs. Default: dirname(dois_tsv)/../wos_pdf
    email      Unpaywall requires an email in the query string.
               Default: PAPER_SEARCH_EMAIL env var (see config.md). Script errors out if unset.

Side-effects:
    Writes <dirname(dois_tsv)>/wos_oa_manifest.json with the OA subset metadata.

Filename convention: {Surname}_{Year}_{TitleAlphaNum}.pdf
"""
import json, os, re, sys, time, urllib.request

def sanitize(s, n=60):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', s or '')
    return re.sub(r'\s+', '_', s.strip())[:n].rstrip('._')

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get('Content-Type', ''), r.url

def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    dois_tsv = os.path.abspath(sys.argv[1])
    default_out = os.path.normpath(os.path.join(os.path.dirname(dois_tsv), '..', 'wos_pdf'))
    out_dir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else default_out
    email = sys.argv[3] if len(sys.argv) > 3 else os.environ.get('PAPER_SEARCH_EMAIL')
    if not email:
        sys.exit('ERROR: Unpaywall requires an email. Set PAPER_SEARCH_EMAIL env var (see config.md) or pass as 3rd arg.')
    os.makedirs(out_dir, exist_ok=True)

    records = []
    with open(dois_tsv, encoding='utf-8') as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if len(p) >= 4:
                records.append(dict(doi=p[0], year=p[1], first=p[2], title=p[3]))

    print(f'Total: {len(records)} | out_dir: {out_dir}', flush=True)
    oa = []; no_oa = 0; no_pdf = 0; fail = 0
    for i, r in enumerate(records, 1):
        try:
            d, _, _ = fetch(f"https://api.unpaywall.org/v2/{r['doi']}?email={email}", timeout=20)
            j = json.loads(d)
        except Exception:
            fail += 1; continue
        if not j.get('is_oa'):
            no_oa += 1; continue
        pdf = (j.get('best_oa_location') or {}).get('url_for_pdf')
        if not pdf:
            no_pdf += 1; continue
        r['pdf_url'] = pdf
        oa.append(r)
        time.sleep(0.15)
    print(f'Unpaywall scan: oa_with_pdf={len(oa)} no_oa={no_oa} oa_no_pdf={no_pdf} fail={fail}', flush=True)

    manifest_path = os.path.join(os.path.dirname(dois_tsv), 'wos_oa_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(oa, f, ensure_ascii=False, indent=1)

    print(f'Downloading {len(oa)} OA PDFs...', flush=True)
    ok, dl_fail = 0, 0
    for i, r in enumerate(oa, 1):
        first = sanitize(r['first'].split('_')[0], 25)
        short = sanitize(re.sub(r'[^A-Za-z0-9 ]', '', r['title']))
        dst = os.path.join(out_dir, f"{first}_{r['year']}_{short}.pdf")
        if os.path.exists(dst) and os.path.getsize(dst) > 50 * 1024:
            continue
        try:
            body, ctype, _ = fetch(r['pdf_url'], timeout=60)
            if len(body) < 10_000 or (b'%PDF' not in body[:1024] and 'pdf' not in ctype.lower()):
                dl_fail += 1
                print(f'[{i}/{len(oa)}] FAIL {r["doi"]}: not PDF (ctype={ctype}, size={len(body)})', flush=True)
                continue
            with open(dst, 'wb') as f:
                f.write(body)
            ok += 1
            print(f'[{i}/{len(oa)}] OK   {os.path.basename(dst)} ({len(body)//1024}KB)', flush=True)
        except Exception as e:
            dl_fail += 1
            print(f'[{i}/{len(oa)}] FAIL {r["doi"]}: {e}', flush=True)
        time.sleep(0.5)
    print(f'Done: ok={ok} fail={dl_fail}', flush=True)

if __name__ == '__main__':
    main()
