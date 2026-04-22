# CNKI 专业检索

提交由 `paper-search` 上游构造的 CNKI 专业检索表达式。本文档**刻意保持"笨"**：不做自然语言解释、不做字段拆分、不做同义词扩展，只负责选子库 + 设筛选项 + 粘表达式 + 点检索 + 返回命中数。

## 入参

`$ARGUMENTS` 是 `paper-search` 阶段 ④ 产出的完整 CNKI 专业检索表达式字符串（即计划里的 `per_db.cnki`）。示例：

```
TKA=('大语言模型'+'大模型') AND TKA=('中医'+'中药'+'中医药') AND TKA=('实体识别'+'命名实体识别')
TI='知识图谱' AND AU='张华平'
TKA=('糖尿病')*('针灸') AND TKA%'随机对照'
```

**关键词字段 = `TKA`**（题名 + 关键词 + 摘要）。`SU`（主题）和 `FT`（全文）索引的是全文主题标签，噪声远超通用词项（`agent` → 饲料添加剂；`Chinese herb*` → 中草药饲料添加剂），一律不进 `per_db.cnki`。

**关键词语言 = 学术中文**。CNKI 主要索引中文题名/关键词/摘要，所以 `per_db.cnki` 中每一个 TKA 词项必须是学术中文。上游 `paper-search` 阶段 ④ 在写出 TKA 之前会把英文查询 token 翻译成对应的中文，即便 `no_expand:true` 也照翻（这是字段语法翻译，不是扩展）。常用映射：

| 英文原词 | 中文 TKA 词项 |
|---|---|
| Retrieval Augmented Generation | 检索增强生成 |
| Large Language Model / LLM | 大语言模型 / 大模型 |
| agent(s) / Multi-Agent / Multiagent | 智能体 / 多智能体 |
| TCM / Traditional Chinese Medicine | 中医 / 中药 / 中医药 |
| Chinese herbal medicine / Chinese herb* | 中草药 |
| electronic health record* | 电子病历 / 电子健康档案 |

**字段码全集**（CNKI 完整字段码）：`SU` 主题 · `TKA` 篇关摘（默认关键词字段）· `TI` 篇名 · `KY` 关键词 · `AB` 摘要 · `CO` 小标题 · `FT` 全文 · `AU` 作者 · `FI` 第一作者 · `RP` 通讯作者 · `AF` 作者单位 · `LY` 期刊名称 · `RF` 参考文献 · `FU` 基金 · `CLC` 中图分类号 · `SN` ISSN · `CN` CN · `DOI` DOI · `QKLM` 栏目信息 · `FAF` 第一单位 · `CF` 被引频次  
**噪声字段——禁止进 `per_db.cnki`**：`SU` · `FT`  
**年度范围**：由专业检索表单的"出版年度"输入框承担（见 Step 2.c′），月/日精度由 `build_refs.py --start/--end` 在客户端兜底。  
**运算符**：`AND` `OR` `NOT`（大写，空格分隔）· `+` 同字段 OR · `*` 同字段 AND · `-` 同字段 NOT · `=` 包含 · `%` 模糊

## 步骤

### 1. 导航

`navigate_page` → `https://{CNKI_HOST}/kns8s/AdvSearch`

`{CNKI_HOST}` 见 `config.md`（直连 `kns.cnki.net` 或机构 VPN 反代）。`?classid=XXXX` 变体会 404，用纯 URL 即可。

### 2. 单次异步 evaluate_script

按顺序执行下面步骤。**选择器稳定性规则**：tab 文案带命中数徽标（例如 `"学术期刊23"`），必须用后端稳定的属性匹配（`a[resource="JOURNAL"]`、`classid="YSTT4HG0"`），不要用 `textContent === '学术期刊'` 精确比较。

a. 切到"学术期刊"子库 → `ul.doctype-menus li a[resource="JOURNAL"]`，`.click()`，等待 1.5 s  
   - 学位论文备选：`a[resource="DISSERTATION"]`
b. 切到"专业检索"tab → `li[name="majorSearch"].click()`，等待 1 s
c. 把表达式粘贴到 `textarea.textarea-major`，走 `Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set` + 派发 `input`/`change` 事件（驱动框架的双向绑定）
c'. 年度范围（按需）：专业检索文本框上方的"出版年度"区域有两个 `<input>`（`placeholder` 分别是"起始年"/"结束年"）。用同样的 value-setter + `input`/`change` 事件派发写入起止年份；选择器以实时 snapshot 为准。**年份值不要塞进 `textarea.textarea-major`**。
d. `.search-btn.click()`，轮询 `.pagerTitleCell`（最长 20 s）
e. 验证码守卫：`#tcaptcha_transform_dy` 可见 → 返回 `{error:'captcha'}` 停手
f. **（`quality_filter:"high"`）应用来源类别筛选**：白名单 = **北大核心 + CSSCI**（仅此两项，不多不少）。

   **作用域**：结果页侧栏 facet 是 `dl[groupid="LYBSM"]`（LYBSM = 来源标识码）。折叠态带 class `is-up-fold off`；点击 `dt.tit` 展开。`dd` 内是一个 `<li>` 列表，每个 `li > input[type=checkbox]` 带 `text="北大核心"` / `text="CSSCI"` 属性，同级 `<span>(N)</span>` 给出该分面的记录数。

   ```javascript
   const dl = document.querySelector('dl[groupid="LYBSM"]');
   const dt = dl.querySelector('dt.tit');
   if (dl.className.includes('off')) { dt.click(); await sleep(1500); }
   for (const name of ['北大核心', 'CSSCI']) {
     const cb = [...dl.querySelectorAll('li input[type="checkbox"]')].find(i => i.getAttribute('text') === name);
     if (cb && !cb.checked) { cb.click(); await sleep(2000); }
   }
   ```

   **双信号交叉校验**：对比勾选前后 `.pagerTitleCell em`（主总数）和各 facet 的 `<span>(N)</span>`（子数）。主总数应降为北大核心 ∪ CSSCI 的并集。如果只有一个信号动（或都不动），说明点到了错的 DOM 作用域——重新 snapshot + 重新定位。

g. **（可选）页大小 = 50**：默认 20 行/页。页大小下拉是**最后一个** `.sort-default`（其 `textContent.trim()` 当前值显示 "20"）；其他 `.sort-default` 是字段/布尔选择器。
   ```javascript
   const all = [...document.querySelectorAll('.sort-default')];
   const pageSizeDrop = all[all.length - 1];
   pageSizeDrop.click();
   await sleep(800);
   const opt50 = [...document.querySelectorAll('li')].find(li => li.offsetParent && li.textContent.trim() === '50');
   if (opt50) { opt50.click(); await sleep(2500); }
   ```
   下一页：`#PageNext`（选择器 `a.pagesnums`；最后一页时带 `.disabled` class）。

返回 `{total, page, url}`。

### 结果集形态：多子库合池

一次全库专业检索返回一个跨子库（期刊 / 硕士 / 博士 / 会议 / 报纸 / 图书 等）合池的结果集。每行的 `td.data` 单元格（纯文本 `"期刊"` / `"硕士"` / `"博士"` / `"中国会议"` 等）标识该条记录来自哪个子库。

`<th>数据库</th>` 表头是纯文本，没有下拉或筛选控件。两种筛选路径：

1. **客户端行级过滤**（推荐，0 次服务端请求）：
   ```javascript
   const journalRows = [...document.querySelectorAll('.result-table-list tbody tr')]
     .filter(r => r.querySelector('td.data')?.innerText.trim() === '期刊');
   ```
   `dm8/API/GetExport` 批量导出模板里的 `keepIdx` 块可以直接加一个 `td.data` 检查。

2. **顶部 doctype tab 服务端过滤**（1 次服务端请求，在需要让后续 facet 计数按单子库重算时用）：
   ```javascript
   document.querySelector('ul.doctype-menus li a[resource="JOURNAL"]').click();
   ```
   合法的 `resource` 值：`JOURNAL` / `DISSERTATION` / `CONFERENCE` / `NEWSPAPER` / `BOOK` / `PATENT` / `STANDARD`。

**来源类别副作用**：Step 2.f 勾选北大核心 / CSSCI 会隐式把结果集限定为期刊论文——因为学位论文、会议论文等子库没有核心期刊标签。所以启用来源类别筛选时，无需再做子库切换。

### 3. 汇报

> CNKI 专业检索：`{expression}` → {total} 命中（{page}）

## 重要说明

- 表达式由 `paper-search` 上游构造。本文档不做任何解释、不扩展同义词。空表达式或非 CNKI 专业检索表达式应显式失败。
- 入口 host：见 `config.md` `{CNKI_HOST}`。
- 下游处理：批量 RIS 导出 —— `references/cnki-delegation.md` §合并管道 的 `dm8/API/GetExport` 模板（内联 reference，不是 leaf skill）。
- selector 漂移时用 `take_snapshot` 重新捕获并调整。始终停留在专业检索 textarea（这是唯一能表达嵌套布尔的入口）。
