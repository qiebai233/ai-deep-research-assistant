# 贡献指南

感谢你愿意为 DeepResearch（AI 深度调研助手）出力！本文档说明开发环境、测试方式与提交流程。
参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 目录

- [可以贡献什么](#可以贡献什么)
- [开发环境](#开发环境)
- [运行测试](#运行测试)
- [代码规范](#代码规范)
- [目录结构](#目录结构)
- [提交与 PR 流程](#提交与-pr-流程)
- [文档与示例](#文档与示例)

## 可以贡献什么

- **Bug 报告**：使用 [Bug 报告模板](.github/ISSUE_TEMPLATE/bug_report.yml)，附复现步骤与环境信息。
- **功能建议**：使用 [功能请求模板](.github/ISSUE_TEMPLATE/feature_request.yml)，说明使用场景。
- **代码**：新 provider、抓取/解析改进、报告排版、Web UI、性能与错误处理。
- **文档**：教程、FAQ、翻译、报告样例。
- **测试**：补充分支覆盖、边界条件与容错场景。

> **硬性边界**：运行时**零第三方依赖**，只允许 Python 3.10+ 标准库；测试**禁止真实联网**。
> 引入依赖或联网测试的 PR 不会被合并。

## 开发环境

需要 Python ≥ 3.10（CI 覆盖 3.10–3.13）与 Git。

```bash
git clone https://github.com/qiebai233/deepresearch.git
cd deepresearch
python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

# 可选：安装为可编辑包，获得 `deepresearch` 命令与开发工具（ruff/build/pytest 配置）
pip install -e ".[dev]"
```

不想装任何依赖也可以直接开发——`python run_tests.py` 会把 `src/` 放进 `sys.path`：

```bash
python run_tests.py            # 全量测试
python run_tests.py -k agent   # 只跑文件名/用例名匹配 agent 的测试
python run_tests.py -v         # 详细输出
```

离线演示（无需任何 API key）：

```bash
python run_tests.py
PYTHONPATH=src python -m deepresearch run "固态电池 2025 产业化进展" --provider mock
```

> Windows PowerShell 设置环境变量：`$env:PYTHONPATH="src"; python -m deepresearch run "..." --provider mock`

## 运行测试

- 统一入口是 `python run_tests.py`（CI 用的也是它），不要另建测试框架。
- 测试必须**完全离线**：需要 HTTP 的地方用 `tests/support.py` 的本地 `LocalServer` 模拟。
- 提交前至少确认：

```bash
python -m compileall -q src
ruff check src tests
python run_tests.py
```

- 新增行为请补测试；修 bug 请先加能复现的测试。

## 代码规范

- 工具链是 [ruff](https://docs.astral.sh/ruff/)：行宽 100，规则 `E, F, W, I, B`（忽略 `B008`）。
- 面向 Python 3.10+，文件顶部写 `from __future__ import annotations`，使用类型标注。
- 公开函数/类写英文 docstring（一句话说明 + 关键行为）；代码注释用英文。
- 库代码不要 `print()`：CLI 用 `Console`，内部用事件（`EventSink`）或返回值。
- 不要吞异常：保留原始原因（日志 / 事件），用户可见错误经 `Console.error` 输出。
- 所有出站 HTTP 必须走 `deepresearch.http.HttpClient`（统一重试、超时、解码、限流）。
- 不要提交运行产物：`reports/`、`.deepresearch/`、`.env`、构建目录都已在 `.gitignore` 中。

## 目录结构

```text
src/deepresearch/
├── models.py        # 数据模型（Plan/Source/Finding/Report…）
├── events.py        # 事件类型与 EventSink
├── errors.py        # 异常层级
├── http.py          # 标准库 HTTP 客户端（统一出口）
├── config.py        # Settings / 环境变量 / 预设 / 校验
├── console.py       # 终端着色与输出
├── api.py           # run_research() 顶层入口
├── storage.py       # 报告落盘（report.md / result.json / trace.jsonl）
├── cli.py           # 命令行
├── llm/             # LLM provider（OpenAI 兼容、mock）
├── search/          # 搜索 provider（Tavily / SearXNG / none / mock）
├── fetch/           # 抓取、正文抽取、缓存
├── agent/           # 流水线编排（planner/researcher/writer）
├── report/          # Markdown 渲染
└── server/          # 标准库 Web 服务 + 静态前端
```

## 提交与 PR 流程

1. **先开 issue 讨论**（较大的功能或行为变更），避免方向不符白做。
2. 从 `main` 拉分支：`feat/short-description`、`fix/short-description`、`docs/...`。
3. 保持提交聚焦；推荐 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：
   `feat: add searxng pagination`、`fix: handle empty tavily results`、`docs: clarify budget flags`。
4. 本地跑完 [运行测试](#运行测试) 与 `ruff check src tests`。
5. 提交 PR，填写 PR 模板：写清动机、改动、验证命令；关联 issue（`Closes #123`）。
6. CI 必须全绿（lint + 3.10–3.13 测试 + 构建）。维护者会做一次人工 review。
7. 不要在 PR 中升级版本号或改 `CHANGELOG.md` 的已发布小节——维护者统一在发布时处理
   （你可以在 `Unreleased` 下补充条目）。

**PR 检查清单**：零新增运行时依赖 · 测试离线 · 新行为有测试 · 文档同步更新 · 不泄露任何密钥。

## 文档与示例

- 用户文档位于 `docs/`，中文为主；英文版为 `README_EN.md`。
- 命令、参数、环境变量必须与代码一致；新增 CLI 参数请同步更新 `README.md` 与 `docs/configuration.md`。
- 报告输出样例见 `examples/`，问题示例见 `examples/sample_questions.md`。
- 截图放在 `assets/`，使用相对路径引用，不要引用外部图床。

## 发布（维护者）

见 [docs/publishing.md](docs/publishing.md)：一键脚本、手动步骤、CI/Release 工作流与占位符替换。
