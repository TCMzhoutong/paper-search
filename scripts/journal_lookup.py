"""ISSN → 期刊分区查表（JCR / 中科院 2025 / 中科院 2026 新锐）。

数据源：`data/jcr.db`（来自 https://github.com/hitfyd/ShowJCR）
- JCR2024 表：JCR 分区 + IF
- FQBJCR2025 表：中科院 2025 升级版（大类 + 小类1-6 + Top）
- XR2026 表：中科院 2026 新锐分区（同结构）

使用：
    from journal_lookup import lookup
    info = lookup('0007-9235')                  # 单 ISSN
    info = lookup('0007-9235', '1542-4863')     # ISSN + EISSN
    # info = {'jcr_q': 'Q1', 'jcr_if': 232.4, 'jcr_cat': 'ONCOLOGY(SCIE)',
    #         'cas25_main': '1区', 'cas25_top': True, 'cas25_subs': [...],
    #         'cas26_main': '1区', 'cas26_top': True, 'cas26_subs': [...]}
首次调用时把三张表加载到内存（~30 MB），之后纯字典查询。
"""
import os, re, sqlite3
from functools import lru_cache

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'data', 'jcr.db')

_INDEX = None  # {normalized_issn: {'jcr':..., 'cas25':..., 'cas26':...}}

def _norm(issn):
    if not issn:
        return None
    s = re.sub(r'[^0-9Xx]', '', issn).upper()
    return s if len(s) == 8 else None

def _quartile_from_cell(cell):
    """e.g. '4 [625/778]' → '4区' ; '1 区' → '1区'"""
    if not cell:
        return None
    m = re.match(r'\s*([1-4])', str(cell))
    return f'{m.group(1)}区' if m else None

def _build_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if not os.path.exists(DB_PATH):
        _INDEX = {}
        return _INDEX
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    idx = {}

    def put(k, key, val):
        if k is None:
            return
        idx.setdefault(k, {})[key] = val

    # JCR2024
    for r in db.execute('SELECT Journal, ISSN, eISSN, Category, "IF(2024)", "IF Quartile(2024)" FROM JCR2024'):
        info = {
            'q': r['IF Quartile(2024)'] or None,
            'if': r['IF(2024)'],
            'cat': r['Category'] or None,
            'journal': r['Journal'] or None,
        }
        put(_norm(r['ISSN']), 'jcr', info)
        put(_norm(r['eISSN']), 'jcr', info)

    # FQBJCR2025 (中科院 2025 升级版) — 仅大类
    for r in db.execute('SELECT Journal, "ISSN/EISSN", "大类", "大类分区", Top FROM FQBJCR2025'):
        info = {
            'cat':     r['大类'] or None,
            'q':       _quartile_from_cell(r['大类分区']),
            'top':     (r['Top'] == '是'),
            'journal': r['Journal'] or None,
        }
        for part in re.split(r'[/,;\s]+', r['ISSN/EISSN'] or ''):
            put(_norm(part), 'cas25', info)

    # XR2026 (中科院 2026 新锐) — 仅大类
    for r in db.execute('SELECT Journal, ISSN, EISSN, "大类英文名", "大类中文名", "大类新锐分区", Top FROM XR2026'):
        info = {
            'cat':     r['大类英文名'] or r['大类中文名'] or None,
            'q':       _quartile_from_cell(r['大类新锐分区']),
            'top':     (r['Top'] == '是'),
            'journal': r['Journal'] or None,
        }
        put(_norm(r['ISSN']),  'cas26', info)
        put(_norm(r['EISSN']), 'cas26', info)

    db.close()
    _INDEX = idx
    return idx

def lookup(issn, eissn=None):
    """Return merged dict for one journal, or {} if not found."""
    idx = _build_index()
    out = {}
    for k in (_norm(issn), _norm(eissn)):
        if k and k in idx:
            for src, info in idx[k].items():
                # first hit wins per source (ISSN > EISSN order)
                out.setdefault(src, info)
    if not out:
        return {}
    flat = {}
    if 'jcr' in out:
        flat['jcr_q']   = out['jcr'].get('q')
        flat['jcr_if']  = out['jcr'].get('if')
        flat['jcr_cat'] = out['jcr'].get('cat')
    if 'cas25' in out:
        c = out['cas25']
        flat['cas25_q']   = c.get('q')
        flat['cas25_cat'] = c.get('cat')
        flat['cas25_top'] = c.get('top')
    if 'cas26' in out:
        c = out['cas26']
        flat['cas26_q']   = c.get('q')
        flat['cas26_cat'] = c.get('cat')
        flat['cas26_top'] = c.get('top')
    return flat

def short_label(info):
    """Compact one-line summary for the summary.md table cell."""
    if not info:
        return ''
    parts = []
    if info.get('jcr_q'):
        s = info['jcr_q']
        if info.get('jcr_if'): s += f"·IF{info['jcr_if']}"
        parts.append(f"JCR {s}")
    if info.get('cas25_q'):
        s = info['cas25_q']
        if info.get('cas25_top'): s += '·Top'
        parts.append(f"中科25 {s}")
    if info.get('cas26_q'):
        s = info['cas26_q']
        if info.get('cas26_top'): s += '·Top'
        parts.append(f"中科26 {s}")
    return ' / '.join(parts)

if __name__ == '__main__':
    import sys, json
    for arg in sys.argv[1:]:
        print(arg, '→', json.dumps(lookup(arg), ensure_ascii=False, indent=2))
