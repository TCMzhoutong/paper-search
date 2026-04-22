#!/usr/bin/env python
"""Search-plan validator & logger for paper-search.

Forcing function for the orchestrator: every search task MUST call this script
before delegating to any leaf skill / API. It validates a structured 4-phase
plan and writes $TEMP/query_log.json (which build_refs.py later re-validates).

The 4 phases (mirrors SKILL.md "核心流程"):

  1. fields       — identify concepts and which search field each lives in
                    (TI / AB / KW / TKA / SU / AU / TS / topic / etc.)
  2. boolean      — normalize the user's intent into an explicit AND/OR/NOT
                    tree (string form, parens allowed)
  3. expansion    — concept-level synonym / bilingual / abbreviation expansion
                    (MAY be skipped — see "Skip-expansion triggers" below)
  4. per_db       — final per-database expression string for EVERY database
                    that will actually be queried

Skip-expansion triggers (phase 3 only — phases 1/2/4 are ALWAYS required):

  Pass --no-expand together with --skip-reason <code>. Allowed codes:
    user_expression       user supplied a concrete boolean expression / query
                          string and asked us to use it as-is
    user_explicit         user explicitly said "不要扩展" / "don't expand" /
                          "use exactly these terms"
    known_id              lookup by DOI / arXiv ID / PMID — no search at all

  When --no-expand is set, the `expansion` field MAY be empty, but `fields`,
  `boolean` and `per_db` are still mandatory.

Usage (full plan via JSON file or stdin):

  python expand_queries.py --plan plan.json
  cat plan.json | python expand_queries.py --plan -

Plan schema (JSON):

  {
    "orig":   "<user's original phrasing>",
    "fields": {
       "<concept_label>": {
         "field": "topic",          # logical field name
         "terms": ["LLM", "Large Language Model", "大语言模型"]
       },
       ...
    },
    "boolean": "(concept_llm) AND (concept_tcm) AND (concept_task)",
    "expansion": {                  # OPTIONAL when --no-expand
       "<concept_label>": ["extra synonym 1", "extra synonym 2"]
    },
    "per_db": {
       "gs":     "(LLM OR \"Large Language Model*\") AND (TCM OR ...) AND (...)",
       "cnki":   "SU=('大语言模型'+'LLM') AND SU=('中医'+'中药') AND SU=(...)",
       "wos":    "TS=((LLM OR ...) AND (TCM OR ...) AND (...))",
       "s2":     "llm tcm entity recognition",
       "pubmed": "(LLM[tiab] OR ...) AND (...)"
    },
    "databases": ["gs", "cnki", "wos", "s2", "pubmed"],
    "no_expand": false,
    "skip_reason": null,
    "allow_single": false
  }

CLI flags also accept the equivalent fields for one-shot use; see --help.

Exit codes:
  0  validated, log written
  2  malformed --plan JSON / missing required field
  3  databases ⊄ per_db keys (some scheduled DB has no built expression)
  4  --no-expand without valid --skip-reason
  5  expansion required (no --no-expand) but `expansion` empty / unchanged
  6  pure-abbreviation term in fields/expansion without full-name context
"""
import argparse, json, os, re, sys
from datetime import datetime

# Force UTF-8 stdout on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

ALLOWED_SKIP = {
    'user_expression', 'user_explicit', 'known_id',
}

ABBREV_BLOCK = {
    'AI', 'TCM', 'LLM', 'LLMs', 'TS', 'ML', 'DL', 'NLP', 'CV', 'RL',
    'KG', 'GAN', 'RAG', 'CNN', 'RNN', 'DNN', 'ViT', 'GNN', 'MoE',
}

def has_full_name_context(q):
    if re.search(r'[\u4e00-\u9fff]', q):
        return True
    return len(re.findall(r'[a-z]{4,}', q)) >= 2

def die(code, msg):
    sys.stderr.write(f'ERROR [exit={code}]: {msg}\n')
    sys.exit(code)

def load_plan(arg):
    if arg == '-':
        text = sys.stdin.read()
    else:
        with open(arg, encoding='utf-8') as f:
            text = f.read()
    try:
        return json.loads(text)
    except Exception as e:
        die(2, f'plan is not valid JSON: {e}')

def validate(plan):
    for k in ('orig', 'fields', 'boolean', 'per_db', 'databases'):
        if k not in plan:
            die(2, f'plan missing required key: {k}')
    if not isinstance(plan['fields'], dict) or not plan['fields']:
        die(2, '`fields` must be a non-empty object')
    if not isinstance(plan['boolean'], str) or not plan['boolean'].strip():
        die(2, '`boolean` must be a non-empty string (AND/OR/NOT tree)')
    if not isinstance(plan['per_db'], dict) or not plan['per_db']:
        die(2, '`per_db` must be a non-empty object')
    if not isinstance(plan['databases'], list) or not plan['databases']:
        die(2, '`databases` must be a non-empty list')

    # rule A: every scheduled DB must have a built expression
    missing = [db for db in plan['databases'] if db not in plan['per_db']
               or not str(plan['per_db'].get(db, '')).strip()]
    if missing:
        die(3, 'databases without per_db expression: ' + ', '.join(missing))

    # rule Q: quality_filter, if set, must be 'high' (only allowed value so far)
    qf = plan.get('quality_filter')
    if qf is not None and qf != 'high':
        die(2, f'quality_filter must be omitted or "high"; got {qf!r}')

    # rule A2: only `cnki` may contain CJK characters in per_db expression
    cjk = re.compile(r'[\u4e00-\u9fff]')
    bad_cjk = [db for db, expr in plan['per_db'].items()
               if db != 'cnki' and cjk.search(str(expr))]
    if bad_cjk:
        die(3, 'non-CNKI databases contain CJK characters in per_db '
               '(only `cnki` may use Chinese terms): ' + ', '.join(bad_cjk))

    # rule B: skip-expansion gating
    no_expand = bool(plan.get('no_expand'))
    reason = plan.get('skip_reason')
    if no_expand:
        if reason not in ALLOWED_SKIP:
            die(4, f'--no-expand requires skip_reason in {sorted(ALLOWED_SKIP)}; '
                   f'got {reason!r}')
    else:
        exp = plan.get('expansion') or {}
        if not isinstance(exp, dict) or not exp:
            die(5, '`expansion` is required unless no_expand=true with valid skip_reason. '
                   'If the user gave a literal expression, set no_expand=true and '
                   'skip_reason="user_expression".')
        # at least one concept got actually expanded
        added = sum(len(v) for v in exp.values() if isinstance(v, list))
        if added == 0:
            die(5, '`expansion` is present but adds zero terms')

    # rule C: each concept must have at least one term with full-name context
    # (a bare abbreviation like "LLM" is fine as long as a sibling term like
    # "Large Language Model" exists in the same concept).
    bad = []
    for label, spec in plan['fields'].items():
        terms = [t for t in ((spec or {}).get('terms') or []) if isinstance(t, str)]
        if not terms:
            continue
        if any(has_full_name_context(t) for t in terms):
            continue
        if any(set(re.findall(r'\b[A-Za-z]{2,5}\b', t)) & ABBREV_BLOCK for t in terms):
            bad.append(f'fields.{label}: {terms!r}')
    if bad:
        die(6, 'concepts contain only pure abbreviations (need at least one '
               'full-name sibling term):\n  - ' + '\n  - '.join(bad))

def write_log(plan):
    tmp = os.environ.get('TEMP') or os.environ.get('TMPDIR') or '/tmp'
    log_path = os.path.join(tmp, 'query_log.json')
    log = dict(plan)
    log['ts'] = datetime.now().isoformat(timespec='seconds')
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return log_path

def render(plan, log_path):
    print(f'## 检索计划（原词："{plan["orig"]}"）\n')
    if plan.get('no_expand'):
        print(f'**Query 扩展**：已跳过（reason=`{plan.get("skip_reason")}`）\n')
    else:
        print('**Query 扩展**：已执行\n')

    print('### ① 字段识别\n')
    print('| 概念 | 字段 | 词项 |')
    print('|---|---|---|')
    for label, spec in plan['fields'].items():
        terms = ', '.join((spec or {}).get('terms') or [])
        print(f'| {label} | `{(spec or {}).get("field","")}` | {terms} |')

    print('\n### ② 布尔归一化\n')
    print(f'```\n{plan["boolean"]}\n```\n')

    if not plan.get('no_expand'):
        print('### ③ 概念扩展\n')
        print('| 概念 | 新增词项 |')
        print('|---|---|')
        for label, terms in (plan.get('expansion') or {}).items():
            print(f'| {label} | {", ".join(terms)} |')
        print()

    print('### ④ 按库构建的最终检索式\n')
    print('| 数据库 | 检索式 |')
    print('|---|---|')
    for db in plan['databases']:
        expr = plan['per_db'][db].replace('|', '\\|')
        print(f'| `{db}` | `{expr}` |')
    print(f'\n✓ 计划已写入 `{log_path}`，build_refs.py 会再次校验。')

def main():
    ap = argparse.ArgumentParser(
        description='Validate and log a 4-phase paper-search plan.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--plan', required=True,
                    help='path to JSON plan file (use "-" for stdin)')
    ap.add_argument('--no-expand', action='store_true',
                    help='override plan.no_expand=true')
    ap.add_argument('--skip-reason', default=None,
                    help='override plan.skip_reason')
    ap.add_argument('--allow-single', action='store_true',
                    help='override plan.allow_single=true')
    args = ap.parse_args()

    plan = load_plan(args.plan)
    if args.no_expand:
        plan['no_expand'] = True
    if args.skip_reason is not None:
        plan['skip_reason'] = args.skip_reason
    if args.allow_single:
        plan['allow_single'] = True

    validate(plan)
    log_path = write_log(plan)
    render(plan, log_path)

if __name__ == '__main__':
    main()
