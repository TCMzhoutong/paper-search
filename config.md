---
description: paper-search skill 的个人配置——API Keys、邮箱、反代 host 等。Claude 和 scripts 的单一事实来源。
---

# 本地个人配置（模板）

> 本文件是**模板**。克隆仓库后请在本地填入你自己的 key/email/host，**不要**把真实值 commit 回仓库。可选：把填好的私有版本保存在其他路径并加入 `.gitignore`，或在 shell 启动脚本里 export 对应环境变量。

所有占位符（`{S2_API_KEY}` / `{UNPAYWALL_EMAIL}` / `{CNKI_HOST}` / `{WOS_HOST}`）在 skill 文档和脚本里引用本文件。运行时 Claude 从这里取值并代入；脚本走下方对应的环境变量。

---

## `{S2_API_KEY}` — Semantic Scholar API Key

- 值：`<YOUR_S2_API_KEY>`（申请入口：https://www.semanticscholar.org/product/api）
- 环境变量：`S2_API_KEY`
- 用法：所有 `api.semanticscholar.org/graph/v1/...` 请求在 Header 加 `x-api-key: {S2_API_KEY}`
- 速率：有 Key 1 req/s；无 Key ~100 req/5min

```bash
curl -H "x-api-key: $S2_API_KEY" "https://api.semanticscholar.org/graph/v1/paper/..."
```

## `{UNPAYWALL_EMAIL}` — Unpaywall 查询邮箱

- 值：`<your-email@example.com>`
- 环境变量：`PAPER_SEARCH_EMAIL`
- 用法：`scripts/wos_oa_download.py` 调 Unpaywall API 时作为 query string 参数（Unpaywall 强制要求邮箱）
- 可传 email 命令行参数覆盖

## `{CNKI_HOST}` — CNKI 访问入口

- 直连主路径：`kns.cnki.net`（有 CNKI 登录态或机构 IP 白名单时）
- 机构 VPN 反代：`<your-institution-cnki-vpn-host>`（典型格式 `https-kns-cnki-net-443.vpn.<institution>.edu.cn`）
- 其他 CNKI 子域（反代格式）：`https-{sub}-cnki-net-443.vpn.<institution>.edu.cn`，常用 `www` / `kns` / `bar` / `navi`

执行前用 `list_pages` 查看当前 host；不在目标 host 上就 `navigate_page` 切过去。后续 `dm8/API/GetExport` 请求用 `location.origin` 自然跟随当前域名。

## `{WOS_HOST}` — Web of Science 访问入口

- 直连：`www.webofscience.com`（需机构订阅 + 登录态）
- 机构 VPN 反代：`<your-institution-wos-vpn-host>`（典型格式 `https-webofscience-clarivate-cn-443.vpn.<institution>.edu.cn`）

直连不可用时用反代。若反代 503 "network unreachable"（命中已下线的 Clarivate CN 负载均衡节点），清该域名下 cookie 后重新 navigate 即可拿到活节点 + 新 SID。

---

## 环境变量速设

```bash
# Linux/macOS
export S2_API_KEY="<YOUR_S2_API_KEY>"
export PAPER_SEARCH_EMAIL="<your-email@example.com>"

# Windows PowerShell
$env:S2_API_KEY = "<YOUR_S2_API_KEY>"
$env:PAPER_SEARCH_EMAIL = "<your-email@example.com>"
```
