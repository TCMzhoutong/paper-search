# CNKI 委托规则

**没有可调的 leaf skill**。所有 CNKI 操作的指引都在 `references/cnki-*.md` 下的 reference doc 里，编排层 Read 后内联执行 chrome-devtools：

| 操作 | 指引文档（Read + 内联执行） |
|---|---|
| 检索 | `references/cnki-advanced-search.md` |
| PDF/CAJ 下载 | `references/cnki-download.md`（逐篇 navigate + click，批量流程见该文 §Batch flow） |
| RIS 批量导出（含摘要/关键词/DOI） | 本文档 §合并管道 的 `dm8/API/GetExport` 模板 |

**严禁** `Skill(cnki-advanced-search)` 等调用——它们不是已注册的顶层 skill，运行时会 `Unknown skill`。编排层的职责：query 扩展、调度、Read 指引、内联执行、合并落盘、结果解释。

## 前置

CNKI 访问入口（`{CNKI_HOST}`）在 `config.md` 定义，直连或机构 VPN 反代两种形态。

执行任一 CNKI reference doc 的 chrome-devtools 步骤前先 `list_pages` 观察当前 host；需要换路径时 `navigate_page` 切到 `{CNKI_HOST}` 即可，后续 `dm8/API/GetExport` 等请求用 `location.origin` 自然跟随当前域名。

## 已知坑

- **滑块验证码**：`#tcaptcha_transform_dy` 可见 → 立即停手报用户手动解，不重试。
- **结果页禁用 `take_snapshot`**：a11y 树 56k+ tokens 会爆输出。用 `evaluate_script` 返回结构化 JSON；必要时 snapshot 加 `filePath` 落 `paper_raw/_tmp/` 再 Read。
- **detail 页 alert "请输入起始年份！"**：每次 `navigate_page` 到 `/kcms2/article/abstract?...` 可能弹。`handleBeforeUnload` 不处理；navigate 后立刻 `handle_dialog("accept")`。
- **下载频控 `errorcode=3`** 与 **PDF 下载逐篇约束**：详见 `references/cnki-download.md` §硬规则 + §1.5。

（浏览器串行 + `location.href` 校验见 SKILL.md 硬规则节）

## 任务分发表

| 任务 | Read + 内联执行的指引文档 |
|------|-------------|
| 论文检索（任意条件：纯关键词 / 来源类别 / 多字段 / 时间范围） | `references/cnki-advanced-search.md` |
| 学位论文检索 | `references/cnki-advanced-search.md` → 结果页点"学位论文"tab |
| 导出引用 RIS（含摘要/关键词/DOI，喂给 build_refs） | 本文档 §合并管道（编排层在结果页 `evaluate_script` 内联执行 `dm8/API/GetExport` 模板） |
| 下载全文 PDF/CAJ | `references/cnki-download.md` |

## 检索约定

- **入参形态**：`references/cnki-advanced-search.md` 描述的检索流程接收一段完整的 CNKI **专业检索表达式字符串**（即 `paper-search` 计划里的 `per_db.cnki`）。字段码 / 运算符 / 示例见同一文档。
- **关键词字段与语言**：`TKA`（篇关摘），词项用学术中文；禁用 `SU`/`FT`。合法字段码全集、翻译映射、formalism 细节在 `references/cnki-advanced-search.md` §Arguments。
- **分库策略**：CNKI 专业检索在全库模式下一次检索 pool 所有子库的命中结果（期刊 / 硕士 / 博士 / 会议 / 报纸 / ...），结果表有 `数据库` 列（`td.data`，纯文本 "期刊" / "硕士" / "博士" 等）标识每条记录的子库。过滤路径：
  - 客户端行级过滤：`rows.filter(r => r.querySelector('td.data').innerText === '期刊')`，0 server request
  - 服务端 tab 过滤：click `ul.doctype-menus li a[resource="JOURNAL"/"DISSERTATION"/...]`，1 refresh；在需要让后续锚点 facet 按单子库重算时使用
  - 导出：`dm8/API/GetExport` 返回的 EndNote 格式随子库变化（期刊有 `%J`/`%@`，学位论文有 `%I`/`%9`），`build_refs.py --cnki` parser 按 `TY` 分情况处理
- **来源类别过滤**：在结果页"来源类别"面板勾选 label → 再点"筛选"按钮统一 refresh。白名单与 UI 序列详见 `references/cnki-advanced-search.md` §Step 2.f。
- **年度范围**：专业检索页"出版年度"UI 两个 input 填起止年份；月/日精度由 `build_refs.py --start/--end` 客户端兜底。UI selector 与操作步骤见 `references/cnki-advanced-search.md` §Step 2.c′。
- **学位论文近年延迟**：限定当年/前一年的学位论文 0 结果属正常（入库延迟），不必重试

## 合并管道（权威来源 = `dm8/API/GetExport`）

列表页无摘要/关键词；完整元数据必须走 CNKI 内部导出 API。

流程：编排层 Read `references/cnki-advanced-search.md` 完成检索 → 在结果页 `evaluate_script` 里内联执行下方模板 → Blob 下载到 `~/Downloads/cnki.ris` → `mv` 到 `./paper_raw/_tmp/cnki.ris` → `build_refs.py --cnki` 解析。

### 内联批量导出模板（在 CNKI 结果页 evaluate_script 执行）

```javascript
async (startDate, endDate) => {
  const API_URL = location.origin + '/dm8/API/GetExport';  // same origin as results page
  const checkboxes = document.querySelectorAll('.result-table-list tbody input.cbItem');
  const rows = document.querySelectorAll('.result-table-list tbody tr');
  const keepIdx = [];
  for (let i = 0; i < rows.length; i++) {
    const d = (rows[i].querySelector('td.date')?.innerText || '').trim().slice(0, 10);
    if (d >= startDate && d <= endDate) keepIdx.push(i);
  }
  const parseEndnote = (text) => {
    const out = { authors: [], keywords: [] };
    if (!text) return out;
    for (const raw of text.replace(/<br\s*\/?>/gi, '\n').split('\n')) {
      const line = raw.trim();
      if (!line.startsWith('%') || line.length < 3) continue;
      const tag = line[1], val = line.slice(2).trim();
      if (tag === 'A') out.authors.push(val);
      else if (tag === 'K') out.keywords = val.split(/[;；,，]/).map(s => s.trim()).filter(Boolean);
      else if (tag === 'T') out.title = val;
      else if (tag === 'J') out.journal = val;
      else if (tag === 'D') out.year = val;
      else if (tag === 'V') out.volume = val;
      else if (tag === 'N') out.issue = val;
      else if (tag === 'P') out.pages = val;
      else if (tag === 'X') out.abstract = val;
      else if (tag === '@') out.issn = val;
      else if (tag === 'R') out.doi = val;
      else if (tag === 'U') out.url = val;
    }
    return out;
  };
  const risLines = [];
  for (const i of keepIdx) {
    const exportId = checkboxes[i].value;
    const listDate = (rows[i].querySelector('td.date')?.innerText || '').trim().slice(0, 10);
    const resp = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ filename: exportId, displaymode: 'GBTREFER,elearning,EndNote', uniplatform: 'NZKPT' })
    });
    const data = await resp.json();
    if (data.code !== 1) continue;  // 通常是未登录
    let endnote = '';
    for (const it of data.data) if ((it.mode || '').toLowerCase() === 'endnote') { endnote = it.value[0]; break; }
    const p = parseEndnote(endnote);
    risLines.push('TY  - JOUR');
    if (p.title) risLines.push('TI  - ' + p.title);
    for (const a of p.authors) risLines.push('AU  - ' + a);
    if (p.journal) { risLines.push('JO  - ' + p.journal); risLines.push('T2  - ' + p.journal); }
    if (p.year) risLines.push('PY  - ' + p.year);
    risLines.push('DA  - ' + listDate.replace(/-/g, '/'));
    if (p.volume) risLines.push('VL  - ' + p.volume);
    if (p.issue) risLines.push('IS  - ' + p.issue);
    if (p.pages) { const mm = p.pages.match(/(\d+)-(\d+)/); if (mm) { risLines.push('SP  - ' + mm[1]); risLines.push('EP  - ' + mm[2]); } }
    for (const k of p.keywords) risLines.push('KW  - ' + k);
    if (p.abstract) risLines.push('AB  - ' + p.abstract);
    if (p.issn) risLines.push('SN  - ' + p.issn);
    if (p.doi) risLines.push('DO  - ' + p.doi);
    if (p.url) { risLines.push('UR  - ' + p.url); risLines.push('L1  - ' + p.url); }
    risLines.push('ER  - '); risLines.push('');
  }
  const blob = new Blob(['\uFEFF' + risLines.join('\n')], { type: 'application/x-research-info-systems' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'cnki.ris';
  document.body.appendChild(a); a.click(); a.remove();
  return { count: keepIdx.length };
};
```
