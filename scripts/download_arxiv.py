#!/usr/bin/env python
"""Download arXiv PDFs for every <entry> in an Atom XML response.

Usage:
    python download_arxiv.py <arxiv.xml> [out_dir]

Defaults:
    out_dir = parent directory of <arxiv.xml>

Filename convention: {FirstAuthorSurname}_{Year}_{ShortTitle}.pdf
Rate-limited at 3 s per request (arXiv's unofficial guidance).
"""
import xml.etree.ElementTree as ET
import re, os, sys, time, urllib.request

NS = {'a': 'http://www.w3.org/2005/Atom'}

def sanitize(s, maxlen=60):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '', s or '')
    s = re.sub(r'\s+', '_', s.strip())
    return s[:maxlen].rstrip('._')

def short_title(title):
    words = re.findall(r'[A-Za-z0-9]+', title or '')
    return sanitize('_'.join(words[:8]))

def short_author(name):
    last = (name or '').strip().split()[-1] if (name or '').strip() else 'Unknown'
    return sanitize(last, 30)

def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    xml_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(xml_path)) or '.'
    out_dir = os.path.abspath(out_dir)
    if not out_dir.endswith(('paper_raw', 'paper_raw/')) and os.path.basename(out_dir) == '_tmp':
        # If caller passes _tmp dir by mistake, drop to its parent (paper_raw)
        out_dir = os.path.dirname(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    tree = ET.parse(xml_path)
    entries = tree.getroot().findall('a:entry', NS)
    todo = []
    for e in entries:
        idv = e.find('a:id', NS).text
        m = re.search(r'abs/(.+?)(v\d+)?$', idv)
        if not m: continue
        arxiv_id = m.group(1)
        title = re.sub(r'\s+', ' ', e.find('a:title', NS).text.strip())
        first = e.findall('a:author', NS)[0].find('a:name', NS).text.strip()
        year = e.find('a:published', NS).text[:4]
        fname = f"{short_author(first)}_{year}_{short_title(title)}.pdf"
        todo.append((arxiv_id, f'https://arxiv.org/pdf/{arxiv_id}', fname))

    print(f'Total: {len(todo)} | out_dir: {out_dir}', flush=True)
    ok, fail, skip = 0, 0, 0
    for i, (aid, url, fname) in enumerate(todo, 1):
        dst = os.path.join(out_dir, fname)
        if os.path.exists(dst) and os.path.getsize(dst) > 10 * 1024:
            skip += 1
            print(f'[{i}/{len(todo)}] SKIP {fname}', flush=True)
            continue
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(dst, 'wb') as f:
                f.write(data)
            ok += 1
            print(f'[{i}/{len(todo)}] OK   {fname} ({len(data)//1024}KB)', flush=True)
        except Exception as ex:
            fail += 1
            print(f'[{i}/{len(todo)}] FAIL {aid}: {ex}', flush=True)
        time.sleep(3)
    print(f'Done: ok={ok} fail={fail} skip={skip}', flush=True)

if __name__ == '__main__':
    main()
