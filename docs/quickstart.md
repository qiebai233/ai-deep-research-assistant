# 快速开始

5 分钟从零到一份带引用的研究报告。只需要 **Python 3.10+**，没有其他运行时依赖。

## 0. 前置要求

- Python **3.10 / 3.11 / 3.12 / 3.13**（`python --version` 检查）
- 可选：`git`（获取源码）、`pip`（安装命令）、Docker（容器部署）
- 真实调研需要：一个 LLM API key（[DeepSeek](https://platform.deepseek.com) 最省事）
  和一个搜索 API key（[Tavily](https://tavily.com)）；**离线演示两者都不需要**

## 1. 30 秒离线体验（不用 key、不联网）

```bash
git clone https://github.com/qiebai233/ai-deep-research-assistant.git
cd deepresearch

# 免安装直接运行（把 src/ 放进 PYTHONPATH）
PYTHONPATH=src python -m deepresearch run "固态电池 2025 产业化进展与主要瓶颈" --demo
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
python -m deepresearch run "固态电池 2025 产业化进展与主要瓶颈" --demo
```

命令会实时打印调研进度，结束时给出摘要与产物路径，大致如下：

```text
  DeepResearch  v0.1.0
  AI 深度调研助手 · 给定问题，自动调研并生成带引用的报告

  问题   固态电池 2025 产业化进展与主要瓶颈
  LLM    mock / mock-researcher
  搜索   mock
  深度   standard（最多 5 个子问题 / 14 个来源）
  语言   zh
· 离线演示模式：不联网、不需要 API key，报告为确定性示例。

  ▶ 开始调研：固态电池 2025 产业化进展与主要瓶颈
  ◈ 已生成研究计划：5 个子问题
  ...
  ★ 报告已完成

──────────────────────────── 完成 ────────────────────────────

✓ 固态电池 2025 产业化进展与主要瓶颈（示例报告）
  章节      5
  来源      6 篇被引用
  发现      5
  LLM 调用  12 次 / 8452 tokens
  成本      免费（mock）
  耗时      0.3s

· 报告：reports/20261026-164611-固态电池-2025-产业化进展与主要瓶颈/report.md
· 数据：reports/.../result.json
· 轨迹：reports/.../trace.jsonl
```

> 以上数字是 mock 模式的确定性示例（具体值以实际输出为准）。**mock 报告不是真实调研结果**，
> 只用于验证安装与体验流程。

养成先关进度看结果的习惯：

```bash
# 只输出 Markdown（适合重定向/管道）
deepresearch run "问题" --demo --stdout > report.md

# 只保留最终摘要
deepresearch run "问题" --demo --quiet
```

## 2. 安装为全局命令

```bash
cd deepresearch

# 可编辑安装（开发/长期使用推荐）
pip install -e .

# 或者只安装一份快照
pip install .

deepresearch version
```

安装后即可直接用 `deepresearch` 命令（脚本入口由 `pyproject.toml` 声明）。
不想改动全局环境时用虚拟环境：

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows:     .venv\Scripts\Activate.ps1
pip install -e .
```

## 3. 接真实的模型与搜索（推荐组合：DeepSeek + Tavily）

1. 获取 key：
   - DeepSeek：<https://platform.deepseek.com> → API Keys → 创建
   - Tavily：<https://tavily.com> → 控制台 → API key（有免费额度）
2. 创建配置：

```bash
cp .env.example .env              # macOS / Linux / Git Bash
Copy-Item .env.example .env       # Windows PowerShell
```

   编辑 `.env`，填入两行（其余留空即可，provider 会自动识别）：

```dotenv
DEEPSEEK_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

   > 也可以不建文件，直接设置环境变量：
   > `export DEEPSEEK_API_KEY=...`、`export TAVILY_API_KEY=...`（PowerShell 用 `$env:NAME="..."`）。

3. 确认配置被正确读取：

```bash
deepresearch providers
```

```text
  当前配置
  LLM provider          deepseek
  LLM model             deepseek-chat
  LLM endpoint          https://api.deepseek.com/v1
  API key               set
  Search provider       tavily
  ...
```

4. 开始真实调研：

```bash
deepresearch run "中国新能源汽车出海在 2025 年面临的主要挑战" --depth standard
```

   - 首次建议 `--depth quick` 试跑，确认 key/网络正常后再用 `standard`/`deep`
   - 想控制花费：`--max-cost 0.10 --max-seconds 300`
   - 想输出英文报告：`--lang en`
   - 想完全离线：`--demo`

更多 provider（OpenAI / OpenRouter / Ollama / vLLM / SearXNG）见 [providers.md](providers.md)。

## 4. 打开 Web 界面

```bash
deepresearch serve --open
```

- 默认地址 <http://127.0.0.1:8000>，`--open` 自动打开浏览器
- 换端口：`deepresearch serve --port 9000`
- 界面上可以：输入问题、选择深度、看实时进度（SSE）、阅读报告、下载 `.md`/`.json`、中英切换
- 健康检查：`curl http://127.0.0.1:8000/api/health`

> Web 服务没有鉴权，默认只绑定 `127.0.0.1`。请勿直接暴露到公网；需要共享时放在带认证的反向代理后。

## 5. 产物在哪里

每次运行都会新建一个目录（不会覆盖历史报告）：

```text
reports/
└── 20261026-164611-固态电池-2025-产业化进展与主要瓶颈/
    ├── report.md     # 最终交付物：摘要 / 关键发现 / 目录 / 分节正文 / 研究局限 / 参考文献
    ├── result.json   # 结构化记录：报告 + 研究状态 + 用量统计（含 schema_version、版本号）
    └── trace.jsonl   # 逐行事件轨迹，用于调试与复现（每行一个 ProgressEvent）
```

- 目录名格式：`{YYYYmmdd-HHMMSS}-{问题 slug}`；重名自动追加 `-2`。
- 修改输出目录：`--out DIR` 或 `DEEPRESEARCH_OUT_DIR`。
- 不要 JSON / trace：`--no-json`、`--no-trace`。
- 报告 Markdown 以链接形式给出参考文献（`[S1] {title} — {url}`），正文引用与来源一一对应。

示例报告见 [examples/sample_report.md](../examples/sample_report.md)，
可复制的真实问题清单见 [examples/sample_questions.md](../examples/sample_questions.md)。

## 6. Docker（可选）

```bash
docker build -t deepresearch:0.1.0 .
docker run --rm -p 127.0.0.1:8000:8000 deepresearch:0.1.0

# 接真实服务：通过 env-file 注入 key（不要 COPY .env 进镜像）
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env deepresearch:0.1.0

# 或使用 compose（带报告目录与缓存卷）
docker compose up --build
```

镜像基于 `python:3.12-slim`，以非 root 用户运行，报告写入容器内 `/data/reports`。

## 7. 下一步

| 想做 | 看这里 |
| --- | --- |
| 了解全部配置项与预算 | [configuration.md](configuration.md) |
| 接入 OpenAI / Ollama / vLLM / SearXNG | [providers.md](providers.md) |
| 了解流水线与模块结构 | [architecture.md](architecture.md) |
| 常见问题 | [faq.md](faq.md) |
| 开发与贡献 | [CONTRIBUTING.md](../CONTRIBUTING.md) |

## 排障速查

| 现象 | 处理 |
| --- | --- |
| `No module named deepresearch` | 未安装且没设 `PYTHONPATH=src`；或不在仓库根目录 |
| `配置错误：... needs an API key` | `.env` 没有生效或 key 为空；用 `deepresearch providers` 确认 |
| 运行很久没输出 | `deep` 模式 + 本地模型会慢；换 `--depth quick` 或看 `--debug` |
| 401 / 429 | key 无效或被限流；检查服务商后台 |
| 报告没有参考文献 | 搜索为 `none` 或抓取全部失败；检查搜索配置与网络 |
| Web 页面打不开 | 端口被占用或 host 不对；换 `--port`，确认防火墙 |
