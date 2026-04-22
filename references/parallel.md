# 并行分治策略

**适用范围：仅 API 库（arXiv / Semantic Scholar / PubMed / PwC）。浏览器驱动库（CNKI / WoS / Google Scholar）禁用本文策略——见 SKILL.md 硬规则"浏览器库 = Skill 工具调 leaf，不是 Agent 工具"。**

任务包含多个**独立**目标时（如同时查询 N 篇论文、N 个来源），分发子 Agent 并行执行。

**好处**：速度 = 单子任务时长；抓取内容不进入主 Agent context，节省 token。

## 子 Agent Prompt 写法

- **不要**让子 agent 加载 paper-search skill 或自查"是否经编排层调用"——这会触发拒绝循环。子 agent 是干活的工人，调度判断由主线程做完
- 给子 agent 完整的目标描述 + 必要事实（URL/DOI/字段需求），不暗示手段
- 描述**目标**（获取/提取/查找），不指定具体步骤
- **注意用词**：「搜索 BERT 的引用数」会把子 Agent 锚定到 WebSearch；应写「获取 BERT 的引用数」

## 典型场景

| 适合分治 | 不适合分治 |
|---------|-----------|
| 多平台并发查同一论文（arXiv + S2 + PubMed） | 查询有依赖关系（先搜索再按结果查详情） |
| 批量查询 N 篇不相关论文 | 简单单平台单次 API 查询 |
| 多个作者主页并行抓取 | 几次 curl 就能完成的轻量任务 |
| 同一数据库的 2-3 个扩展 query 并行跑 | — |

## 结果合并

子 Agent 返回的 per-source 中间件落 `paper_raw/_tmp/`，由 `scripts/build_refs.py` 统一合并去重（DOI > arXiv ID > WoS ID > title+year 模糊匹配）。
