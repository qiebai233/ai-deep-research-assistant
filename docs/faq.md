# 常见问题（FAQ）

## 基础

### DeepResearch 是什么？

输入一个研究问题，Agent 自动完成「问题拆解 → 多轮检索 → 抓取正文 → 提炼带引用的发现 →
反思证据缺口并补检 → 生成大纲 → 分节写作 → 输出带参考文献的 Markdown 报告」。
两个入口：命令行（`deepresearch run`）和本地 Web UI（`deepresearch serve`）。

### 和 ChatGPT / Perplexity 有什么区别？

定位不同，不比较模型强弱。本项目的差异点在于：

- **完全可自持**：零第三方运行时依赖，可离线 mock 运行，也可接任意 OpenAI 兼容端点 + 自建 SearXNG；
- **报告结构固定**：摘要 / 关键发现 / 目录 / 分节正文 / 研究方法与局限 / 参考文献 / 免责声明，
  产物同时落盘 `report.md` + `result.json` + `trace.jsonl`；
- **引用可核查**：正文 `[S1]` 与参考文献一一对应，只保留真正抓取并引用过的来源；
- **可嵌入**：一个 `run_research()` 调用即可接入自己的程序。

### 不配置任何 API key 能用吗？

能。默认配置就是离线 mock（`--provider mock --search mock`，或直接 `--demo`），
不联网、无 key，产出确定性的示例报告，适合体验流程、看产物结构、跑测试。
但 mock 内容是模板化的，**不能当作真实调研结论**。

### 需要哪些 key？

最少一个 LLM key（DeepSeek / OpenAI / OpenRouter 等）。想要外部引用还需要搜索 key（Tavily）
或自建 SearXNG。本地模型（Ollama / vLLM）不需要 LLM key。

## 安装与运行

### `No module named deepresearch` 怎么办？

三种原因：没有安装、不在仓库根目录、或者想免安装运行但没设置 `PYTHONPATH`。
最省事的是 `pip install -e .` 后用 `deepresearch` 命令；免安装则必须：

```bash
PYTHONPATH=src python -m deepresearch run "问题" --demo
```

### Windows 上命令怎么设置环境变量？

```powershell
$env:PYTHONPATH = "src"          # 仅当前 PowerShell 会话
$env:DEEPSEEK_API_KEY = "sk-..."
python -m deepresearch run "问题"
```

cmd 用 `set PYTHONPATH=src && python -m deepresearch run "问题"`。

### 支持 Python 3.9 吗？

不支持，最低 3.10（CI 覆盖 3.10–3.13）。用到的语法与标准库特性以 3.10 为基线。

### 需要装 Node.js / 数据库 / Redis 吗？

不需要。没有前端构建步骤，没有数据库；Web UI 是原生 HTML/CSS/JS，由 Python 标准库服务。
唯一会写盘的是报告目录与抓取缓存。

## 配置

### `.env` 和 `deepresearch init` 生成的文件有什么区别？

- 仓库里的 `.env.example`：全字段注释模板，**默认等价于离线 mock**，复制后不改也能跑；
- `deepresearch init`：生成一份预填 `deepseek` + `tavily` 占位 key 的简短模板，
  适合已经决定用 DeepSeek + Tavily 的用户，需要替换占位值才能联网。

### 改了配置不生效？

按优先级检查：CLI 参数 > 真实环境变量 > `.env` > 默认值。常见坑：

- 在错误的目录运行（`.env` 默认从**当前工作目录**读取）；
- 上一节 shell 里 `export` 的变量还生效，覆盖了 `.env`；
- 用来确认：`deepresearch providers`（会显示最终解析结果）。

### 怎么临时切配置？

用全局参数 `--env-file`（注意要放在子命令前面）：

```bash
deepresearch --env-file .env.prod run "问题"
```

### 怎么确认当前用的是什么模型/搜索？

```bash
deepresearch providers
```

会打印当前配置、各 LLM 预设状态、搜索后端状态，以及非致命告警。

## 质量与成本

### 报告里的内容可靠吗？

报告由模型汇总生成，**可能存在错误、过时信息或误引**。请把它当作「研究起点 + 线索集合」，
关键结论回到原文核实。每份报告末尾都带有免责声明。

### 怎么提高报告质量？

1. 问题写具体：时间、地域、对象、比较维度（见 [sample_questions.md](../examples/sample_questions.md)）；
2. 用更强的模型并适当提高 `DEEPRESEARCH_LLM_TEMPERATURE` 之外的设置（温度越低越稳定）；
3. 用 `--depth deep` 增加子问题、来源与反思轮数；
4. 换质量更高的搜索（Tavily 通常优于自建小实例）；
5. 对争议话题要求报告呈现反面证据与「仍待验证」项。

### 为什么报告引用很少甚至没有？

- 搜索为 `none`：只依赖模型知识，没有外部引用；
- 抓取全部失败（网络受限、目标站点反爬、非 HTML）：来源标记 failed，不进入参考文献；
- 查看 `trace.jsonl` 中的 `warning` 事件可定位具体原因。

### 一次运行要花多少钱？

取决于模型、深度与报告长度。`mock` 免费；`deepseek-chat` + `standard` 通常远低于 0.1 美元；
`gpt-4o` + `deep` 会显著更高。用 `--max-cost USD` 设置预算上限，超限后会用已有材料完成报告。
费用数字是**基于内置价目表的估算**，不等于实际账单。

### 为什么我的费用显示为 0？

模型不在内置价目表里时按 0 估算（例如自定义/本地模型）。这不代表免费，只是没有价格数据；
请用 `--max-seconds` / `--max-llm-calls` 控制消耗（后者只能通过环境变量设置）。

### 运行很慢怎么办？

- `deep`（7 子问题 / 24 来源 / 3 轮）本身就慢；先用 `--depth quick` 验证链路；
- 本地模型（Ollama/vLLM）推理慢，建议 `--max-seconds 900` 并降低深度；
- 抓取受目标站点响应影响，可降低 `DEEPRESEARCH_FETCH_CONCURRENCY` 避免被限流（但更慢）；
- 打开缓存（默认开启）可让重复 URL 不再抓取。

## 输出

### 报告在哪里？

默认 `reports/<时间>-<问题>/report.md`，同目录还有 `result.json` 与 `trace.jsonl`。
改目录用 `--out DIR`；不落盘用 `--no-save`；只要 Markdown 文本用 `--stdout`。

### 能导出 PDF / Word 吗？

当前版本只输出 Markdown（这是 v0.1.0 的已知限制）。可用任意 Markdown 工具转换：

```bash
pandoc reports/xxx/report.md -o report.pdf
```

### `result.json` / `trace.jsonl` 是什么？

- `result.json`：结构化完整记录（`schema_version`、版本、问题、`report`、研究 `state`、`usage`、脱敏后的 `settings`）；
- `trace.jsonl`：逐行一个进度事件（`type`/`message`/`data`/`percent`/`at`），可用来复现失败现场或做可视化。

## Web UI 与部署

### 端口被占用 / 想改地址？

```bash
deepresearch serve --port 9000
deepresearch serve --host 0.0.0.0   # 局域网可访问（注意：没有鉴权！）
```

### 能部署到服务器给团队用吗？

技术上可以，但 Web UI **没有认证、没有 CSRF/限速**。请只在可信网络内使用，
或放在 Nginx/Caddy 等带认证与 HTTPS 的反向代理后面，并限制访问来源。
Docker 部署见 [quickstart.md](quickstart.md#6-docker可选)。

### 公司网络要走代理怎么办？

标准的 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 环境变量会被 Python `urllib` 自动读取，
抓取与 LLM 请求都会走代理。若代理需要认证，把凭据写进代理 URL（注意不要泄露到日志）。

## 开发

### 为什么坚持零第三方依赖？

便于审计、部署与嵌入：一个 `python` 命令即可运行，没有依赖冲突与供应链风险。
代价是部分能力（PDF 解析、复杂 HTML 清洗、浏览器渲染）需要自己实现或不支持。

### 怎么新增一个 LLM / 搜索 provider？

在对应目录实现协议（`LLMClient` / `SearchProvider`），在工厂函数与 `PRESETS` 中注册即可，
不需要改流水线。详见 [architecture.md#9-扩展点](architecture.md#9-扩展点) 与 [CONTRIBUTING.md](../CONTRIBUTING.md)。

### 为什么测试不能联网？

CI 与本地测试必须可重复、可在无网络环境运行，也避免消耗真实额度。需要 HTTP 的地方用
`tests/support.py` 的本地 stdlib 服务模拟；端到端测试用 mock 三件套。

### 可以用它做商业项目吗？

代码以 MIT 许可发布，可商用。但请注意：报告会引用并摘录第三方网页内容，转载/商用前
需自行确认来源的版权与使用条款；模型输出也需自行承担合规责任。见 [LICENSE](../LICENSE)。
