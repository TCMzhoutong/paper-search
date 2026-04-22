# WoS 委托规则

**没有可调的 leaf skill**。所有 WoS 操作都在本文档里，编排层 Read 后内联执行 chrome-devtools：

| 操作 | 指引 |
|---|---|
| UI 高级检索 → 导 Plain text | 本文 §检索流程 + §合并管道 |
| OA PDF 下载 | `references/wos-download.md`（Unpaywall API + curl，无浏览器依赖） |

**严禁** `Skill(wos-search)` / Agent + `general-purpose` 包一层 sub-agent 自写 UI 序列——前者未注册会 `Unknown skill`，后者绕过既定 UI 序列和权威导出管道。

## 前置

用户的 WoS 访问经由机构 VPN 反代域名 `{WOS_HOST}`。执行任一 chrome-devtools 步骤前，先用 `list_pages` 确认浏览器已在该反代域名下；若不在，先 `navigate_page` 到 `https://{WOS_HOST}/wos/woscc/advanced-search`。直连 `webofscience.com` 不可用。

**负载均衡死节点**：反代偶见 503 "network unreachable"（命中已下线的 Clarivate CN 节点 `119.188.204.76`）。清掉当前域名下 cookie 后重新 navigate 即可拿到新 SID + 活节点。

## 检索流程（UI 高级检索）

1. `navigate_page` → `https://{WOS_HOST}/wos/woscc/advanced-search`
2. `evaluate_script` 把完整 WoS advanced-search 表达式写进检索框 `textarea#advancedSearchInputArea`（或当前页命名的 textarea 主控件，以 `take_snapshot` 为准），走框架的 value setter + `input`/`change` 事件派发。
3. `evaluate_script` 点击 `button.search-btn-advSearch`（文案含 "Search"），轮询 `app-record` 出现或 `.search-results` 路径就位。
4. 结果页触发 §合并管道 的 Plain text 导出。

**检索式约定**（在表达式本体里写，不要拆 UI）：
- 字段码：`TS=` 主题 / `TI=` 题名 / `AU=` 作者 / `DO=` DOI / `SO=` 来源 / `PY=` 年份 / `DOP=` 发表日期（`YYYY-MM-DD/YYYY-MM-DD`）/ `OG=` 机构 / `AB=` 摘要 / `FO=` 基金 / `CU=` 国家 / `LA=` 语言 / `DT=` 文献类型。
- 默认过滤：`AND LA=English AND DT=(Article OR Review)`，用户显式覆盖时才改。相对日期一律换成绝对 `DOP=YYYY-MM-DD/YYYY-MM-DD`。
- edition 筛选：用户提 SCI/SSCI 时通过 UI 左侧 Editions 复选框（或结果页 Refine 面板），不要塞进表达式。

## 合并管道（权威来源 = WoS 原生 Plain text 导出）

**不走 DOM/API 字段抽取**。WoS 结果页和 API 返回的字段不包含完整摘要；完整元数据走 WoS 自带的 Plain text 导出。

导出参数：
- 格式：`Export → Plain text file`
- Record Content：`Author, Title, Source, Abstract`（一次导出请求轻量，避免 RIS Full Record 在 500+ 条量级触发 `saveToFile 500`）
- Record Options：总结果 ≤ 1000 时选 `All records on page`，一次导出全部；> 1000 时选 `Records from:` 分批，单批 ≤ 1000

标准流程：

1. 按 §检索流程 完成检索 → 结果页
2. 编排层在结果页 `evaluate_script` 内联触发 `Export → Plain text file` UI，按结果量选 `All records on page` 或 `Records from:` 分批；浏览器下载到 `~/Downloads/savedrecs.txt`
3. 编排层 `mv ~/Downloads/savedrecs.txt ./paper_raw/_tmp/wos.txt`（多批则每批落盘后 concat）
4. `scripts/build_refs.py --wos ./paper_raw/_tmp/wos.txt` 解析

`paper_raw/_tmp/wos.txt` 是权威来源。
