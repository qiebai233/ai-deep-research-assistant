# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [Unreleased]

### Planned

- 报告导出 PDF / DOCX（当前仅 Markdown，可自行转换）。
- 更多搜索后端与抓取解析策略（当前为 Tavily / SearXNG / none / mock）。
- 可选的持久化与多用户会话（当前 Web UI 仅内存保留最近 20 次运行）。

## [0.1.0] - 2026-10-26

首个公开版本。**Beta**：核心流水线可用、测试覆盖完整，但接口仍可能小幅调整。

### Added

- **研究流水线**：Planner（问题拆解）→ Researcher（检索 + 并发抓取 + 提炼带引用发现）
  → Reflect（识别证据缺口、补检）→ Writer（大纲 + 分节写作 + 元信息）→ Render
  （Markdown 报告：摘要 / 关键发现 / 目录 / 分节正文 / 研究方法与局限 / 参考文献 / 免责声明）。
- **深度预算**：`quick`（3 子问题 / 8 来源 / 1 轮）、`standard`（5 / 14 / 2）、`deep`（7 / 24 / 3）。
- **LLM 接入**：任意 OpenAI 兼容 `/chat/completions` 接口，内置 DeepSeek / OpenAI / OpenRouter /
  Ollama / 自定义端点预设，以及完全离线的确定性 `mock`。
- **搜索接入**：Tavily、SearXNG（自建）、`none`（纯模型知识）、`mock`（离线合成结果）。
- **抓取与提取**：标准库 `html.parser` 正文抽取（去脚本/导航/页脚等噪声）、并发抓取、
  失败降级、带 TTL 的本地文件缓存。
- **CLI**：`deepresearch run / serve / providers / init / version`，中文输出（`--lang en` 切英文），
  支持 `--depth`、`--provider`、`--model`、`--search`、`--out`、预算与开关参数。
- **Web UI**：`deepresearch serve` 启动标准库 HTTP 服务（默认 `http://127.0.0.1:8000`），
  问题输入、深度选择、SSE 实时进度、报告渲染与下载、最近运行列表、中英切换、深浅色自适应。
- **可观测性**：统一事件流（`run_start` → … → `run_end`），可选 `trace.jsonl` 事件轨迹；
  结构化 `result.json` 包含报告、状态与用量统计。
- **预算保护**：`max_llm_calls` / `max_cost_usd` / `max_seconds` 超限时软停止并写入报告局限。
- **配置**：`DEEPRESEARCH_*` 环境变量、`.env` 文件、厂商变量自动识别、预设置与校验。
- **工程**：零第三方运行时依赖（Python ≥ 3.10 标准库）；`python run_tests.py` 一键测试；
  GitHub Actions CI（Python 3.10 / 3.11 / 3.12 / 3.13 矩阵：ruff + 测试 + 构建产物）；
  tag 触发的 Release 工作流（sdist/wheel + 自动 release notes）；Dockerfile 与 Compose；
  `scripts/publish.ps1` / `scripts/publish.sh` 一键建仓、推送、打 tag。

### Known limitations

- 报告为 Markdown 文本，未内置 PDF / DOCX 导出。
- 费用数字基于 `config.py` 内的近似价目表，仅用于预算控制参考，不等于实际账单。
- 未知模型（不在价目表内）的费用不参与估算，`est_cost_usd` 可能为 0。
- 抓取器只做静态 HTML 正文提取，不执行 JavaScript，SPA 页面可能抓取质量低。
- 缓存无容量上限，也没有后台清理；删除 `DEEPRESEARCH_CACHE_DIR` 目录即可重置。
- Web UI 无鉴权，默认仅绑定 `127.0.0.1`；请勿直接暴露到公网。
- `mock` 模式产出确定性示例内容，**不是真实调研结果**，仅用于演示与测试。
- 单个搜索请求失败只会降级（返回空结果），不会重试整轮研究。

[Unreleased]: https://github.com/qiebai233/ai-deep-research-assistant/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/qiebai233/ai-deep-research-assistant/releases/tag/v0.1.0
