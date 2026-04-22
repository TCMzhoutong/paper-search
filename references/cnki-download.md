# CNKI 论文下载

## 核心模式

一次一 PDF：`navigate_page(detail_url, handleBeforeUnload:"accept")` → `evaluate_script` 轮询 `#pdfDown` 并 `.click()` → 脚本内节流 sleep → 下一个 URL。点击保留元素原生的 `target="_blank"`；新 tab 接收来自 `bar.cnki.net` 的 `Content-Disposition` 响应，浏览器自动下载，原详情页 tab 保留供下一轮使用。

## 前置

- 已登录 CNKI（检测：详情页 `.downloadlink.icon-notlogged` 不存在）
- `{CNKI_HOST}/kcms2/article/abstract?v=...` 可直连（host 见 `config.md`）
- 目标目录就绪，例如 `./paper_raw/cnki_pdf/`

## 批量流程（RIS 驱动）

### Step A. 从 `cnki.ris` 构建 URL 队列

`build_refs.py --cnki` 产出的 RIS 每条记录带 `TI` 和以下两种 `UR` 形式之一。入队前统一预解析为同源 `kns.cnki.net`：

| URL 形式 | 处理 |
|---|---|
| `https://kns.cnki.net/kcms2/article/abstract?v=...` | 原样入队 |
| `https://link.cnki.net/doi/<DOI>` | 发一次禁跳转 GET，读 301 响应的 `Location` 头，把它指向的 `kns.cnki.net` URL 入队 |

同源入队很重要：整个循环跑在 `kns.cnki.net` 域下，cookies、sessionStorage、登录态才不会丢。参考解析器（Python）：

```python
import urllib.request
class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'stop', headers, fp)
opener = urllib.request.build_opener(NoRedir)
try:
    opener.open(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=15)
    resolved = url
except urllib.error.HTTPError as e:
    resolved = e.headers.get('Location', url) if e.code in (301,302,303,307,308) else url
```

### Step B. 单 URL 循环体

每个 URL 两次工具调用：

```
navigate_page({ url: URL_i, handleBeforeUnload: "accept" })
```

```javascript
async () => {
  let p;
  for (let i = 0; i < 30; i++) {
    p = document.querySelector('#pdfDown');
    if (p) break;
    await new Promise(r => setTimeout(r, 400));
  }
  if (!p) return { err: 'no pdf', url: location.href };
  const t = document.querySelector('.brief h1')?.innerText?.trim();
  p.click();
  await new Promise(r => setTimeout(r, DELAY_MS));
  return { clicked: true, t };
}
```

`DELAY_MS` 起步 `4500`；每 3 次点击用 `9500`（见 Step C）。

### Step C. 限频 + 验证码处理

连续点击会触发 CNKI 弹出验证 tab，有两种形态：

- `bar.cnki.net/bar/verify/index.html?...errorcode=3` 被激活 → 立即停止循环，向用户汇报"验证码触发，已点击 N 条"，请用户在 Chrome 里手动解滑块
- `bar.cnki.net/bar/verify/verifySuccess.html` → 静态成功页，跳过

用户确认解完验证码后，恢复循环但把 `DELAY_MS` 固定为 `20000`；这个节奏保持到批次结束。

### Step D. 循环后一次性 mv

```bash
mv ~/Downloads/*.pdf ./paper_raw/cnki_pdf/
```

CNKI 直接以 `"{title}_{first-author}.pdf"` 命名下载到 Downloads。整批跑完或在验证码暂停点一次性 mv 即可。

## 单篇（交互式，基于当前页）

当前浏览器已在目标详情页时，跑一次下面的 `evaluate_script`。它比 Step B 多做了验证码/登录态前置检查：

```javascript
async () => {
  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) return { error: 'captcha' };
  const notLogged = document.querySelector('.downloadlink.icon-notlogged');
  if (notLogged) return { error: 'not_logged_in' };
  const pdf = document.querySelector('#pdfDown') || document.querySelector('.btn-dlpdf a');
  if (!pdf) return { error: 'no_download' };
  const title = document.querySelector('.brief h1')?.innerText?.trim()?.replace(/\s*网络首发\s*$/, '') || '';
  pdf.click();
  return { status: 'downloading', title };
}
```

CAJ 备选：`#cajDown` / `.btn-dlcaj a`。

## 已知弹窗

部分 VPN 反代构建在 `navigate_page` 落到详情页时会触发 `alert("请输入起始年份！")`（首页遗留的日期校验脚本）。工具结果里会看到 `# Open dialog`；立刻 `handle_dialog(action:"accept")`。这是经典的 `alert()` dispatch；`navigate_page` 的 `handleBeforeUnload` 参数作用于另一个 hook，覆盖不到这个。

## 验证过的选择器

| 元素 | 选择器 |
|---|---|
| PDF 下载链接 | `#pdfDown`（备选 `.btn-dlpdf a`） |
| CAJ 下载链接 | `#cajDown`（备选 `.btn-dlcaj a`） |
| 标题 | `.brief h1`（末尾剥离"网络首发"） |
| 未登录指示 | `.downloadlink.icon-notlogged` |
| 验证码容器 | `#tcaptcha_transform_dy`（`getBoundingClientRect().top >= 0` 时为激活态） |

## 工具调用开销

- 单篇：1–2 次（navigate_page + evaluate_script）
- 批量 N 条：2N + 1 次（末尾一次 `mv`）。验证码打断再加 1 次。
