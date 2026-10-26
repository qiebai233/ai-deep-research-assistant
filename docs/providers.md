# Provider 接入

DeepResearch 需要两类外部服务，二者都可以替换：

| 类别 | 作用 | 内置实现 |
| --- | --- | --- |
| **LLM** | 规划、提炼发现、写作、生成元信息 | 任意 OpenAI 兼容 `/chat/completions` 接口（DeepSeek / OpenAI / OpenRouter / Ollama / vLLM / 自建网关）+ 离线 `mock` |
| **搜索** | 发现候选网页 | Tavily、SearXNG（自建）、`none`（不搜索）、`mock`（离线） |

网页抓取不需要单独配置：选定搜索后，内置抓取器会自动抓取结果页并提取正文
（可调超时、并发、缓存，见 [configuration.md](configuration.md)）。

## 怎么选

| 场景 | LLM | 搜索 | 特点 |
| --- | --- | --- | --- |
| 先跑通、看流程 | `mock` | `mock` | 零配置、零成本、不联网；内容是确定性示例 |
| 日常中文调研（推荐） | `deepseek` + `deepseek-chat` | `tavily` | 成本低、质量好、接入快 |
| 已有 OpenAI 额度 | `openai` + `gpt-4o-mini` | `tavily` | 稳定，价格略高于 DeepSeek |
| 一个 key 用多家模型 | `openrouter` | `tavily` | 模型选择灵活 |
| 数据不能出内网 | `ollama` / `vllm`（本地） | `searxng`（自建） | 全链路自持，需自备算力 |
| 只想要模型知识、不要网页 | 任意真实 LLM | `none` | 无外部引用，仍有参考价值但不可核查 |

## LLM 接入

所有 LLM 走同一条协议：`POST {base_url}/chat/completions`，`Authorization: Bearer {key}`。
因此只要服务商兼容 OpenAI 接口，就能直接用。切换方式三选一：

```bash
# 1. CLI 参数
deepresearch run "问题" --provider deepseek --model deepseek-chat

# 2. 环境变量（当前会话）
$env:DEEPRESEARCH_LLM_PROVIDER = "deepseek"     # PowerShell
# export DEEPRESEARCH_LLM_PROVIDER=deepseek     # bash

# 3. .env 文件
DEEPRESEARCH_LLM_PROVIDER=deepseek
DEEPRESEARCH_LLM_MODEL=deepseek-chat
```

> 只填 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` 时 provider 会自动识别，
> 见 [configuration.md#provider-自动检测](configuration.md#provider-自动检测)。

### DeepSeek

1. 注册并登录 <https://platform.deepseek.com>。
2. 进入 **API Keys** 页面，创建 key（只显示一次，请立即保存）。
3. 配置：

```dotenv
DEEPSEEK_API_KEY=sk-...
# 可选：DEEPRESEARCH_LLM_MODEL=deepseek-reasoner
```

- 默认模型 `deepseek-chat`；`deepseek-reasoner` 推理更强但更慢、更贵。
- 端点由预设自动填充为 `https://api.deepseek.com/v1`。
- 计费与限流以官网为准；本项目只做近似费用估算（见 [configuration.md#费用估算](configuration.md#费用估算)）。

### OpenAI

1. 登录 <https://platform.openai.com>，在 **API keys** 创建 key。
2. 配置：

```dotenv
OPENAI_API_KEY=sk-...
# 可选：DEEPRESEARCH_LLM_MODEL=gpt-4o-mini
```

- 默认模型 `gpt-4o-mini`；需要更强写作可换 `gpt-4o`（成本显著上升，建议配 `--max-cost`）。
- 需要组织/项目头时可自行设置 `DEEPRESEARCH_LLM_BASE_URL` 或网关。

### OpenRouter

1. 登录 <https://openrouter.ai>，在 **Keys** 创建 key。
2. 配置：

```dotenv
OPENROUTER_API_KEY=sk-or-...
DEEPRESEARCH_LLM_MODEL=openai/gpt-4o-mini
```

- 模型名带厂商前缀（如 `anthropic/claude-3.5-haiku`、`deepseek/deepseek-chat`），以 OpenRouter 模型页为准。
- 部分模型有额外参数或路由策略，本项目不设置这些高级参数，只用标准 chat completions。

### Ollama（本地模型）

1. 安装 <https://ollama.com> 并启动服务（默认监听 `127.0.0.1:11434`）。
2. 拉取模型：

```bash
ollama pull qwen2.5:7b
```

3. 配置（Ollama 提供 OpenAI 兼容端点，所以 `provider=ollama` 无需 key）：

```dotenv
DEEPRESEARCH_LLM_PROVIDER=ollama
DEEPRESEARCH_LLM_BASE_URL=http://localhost:11434/v1
DEEPRESEARCH_LLM_MODEL=qwen2.5:7b
```

- 7B 级模型在「严格输出 JSON」上不如云端模型稳定，流水线会自动重试/兜底，但**报告质量会下降**。
- 本地推理慢：建议 `DEEPRESEARCH_MAX_SECONDS` 放宽，并用 `--depth quick` 试跑。
- 远程 Ollama 记得改 `llm_base_url`，并注意其默认无鉴权，不要暴露到公网。

### vLLM / 其他 OpenAI 兼容服务

适用于 vLLM、LM Studio、LocalAI、FastChat、公司内部 LLM 网关等：

```bash
# 示例：vLLM 启动一个 OpenAI 兼容服务
vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000
```

```dotenv
DEEPRESEARCH_LLM_PROVIDER=custom
DEEPRESEARCH_LLM_BASE_URL=http://localhost:8000/v1
DEEPRESEARCH_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
# 需要鉴权时：
# DEEPRESEARCH_LLM_API_KEY=...
```

- `provider=custom` **必须**显式提供 `llm_base_url` 与 `llm_model`，否则启动时报配置错误。
- 端点必须兼容 `POST /chat/completions`；若服务端不支持 `response_format`（JSON mode），
  在需要结构化输出的环节可能报错，建议换支持该特性的模型/版本。

### 离线 mock

```bash
deepresearch run "任意问题" --demo
# 等价于：--provider mock --search mock
```

`mock` 会走完整的五阶段流水线（虚假但确定性的搜索结果、正文、findings、报告），
**不联网、不需要 key**，用于演示、测试与文档截图。报告内容是模板化的，不能当作调研结论。

## 搜索接入

### Tavily（推荐）

1. 注册 <https://tavily.com>，在控制台获取 API key（有免费额度，额度与价格以官网为准）。
2. 配置：

```dotenv
TAVILY_API_KEY=tvly-...
# 可选，更全但更慢更贵：DEEPRESEARCH_TAVILY_SEARCH_DEPTH=advanced
```

- 默认 `search_depth=basic`、每条 query 取 6 条结果（`DEEPRESEARCH_SEARCH_MAX_RESULTS`）。
- Tavily 返回内容摘要，本项目只把它当作候选 URL + 摘要，正文仍会自行抓取。
- 搜索结果会缓存在本地（`.deepresearch/cache`），但 Tavily 的检索请求本身每次都会发出。

### SearXNG（自建元搜索）

SearXNG 是开源的元搜索引擎，聚合 Google/Bing 等结果，适合内网或不想绑定商业 API 的场景。

1. 启动实例（示例，详细部署见 [SearXNG 官方文档](https://docs.searxng.org/)）：

```bash
docker run -d --name searxng -p 8888:8080 \
  -v ./searxng:/etc/searxng \
  searxng/searxng:latest
```

2. **开启 JSON 输出**：编辑实例的 `settings.yml`，确保包含：

```yaml
search:
  formats:
    - html
    - json
```

   未开启时请求会返回 403/400，本项目会收到搜索失败。

3. 验证：

```bash
curl "http://localhost:8888/search?q=test&format=json"
```

4. 配置：

```dotenv
DEEPRESEARCH_SEARCH_PROVIDER=searxng
SEARXNG_URL=http://localhost:8888
```

- 需要启用 **limiter/botdetection** 的实例请放行本机请求，否则会被限流。
- 公网实例的可用性不稳定，建议自建并对内网开放。

### 不使用搜索（none）

```bash
deepresearch run "某个概念的通俗解释" --search none
```

报告完全依赖模型已有知识，**没有外部引用与参考文献**，适合解释类问题；
遇到时效性或需要数据支撑的问题不建议使用。

### 离线合成（mock）

`--search mock` 返回固定的合成结果（arxiv/nature/wikipedia 等固定域名池），用于测试与演示。
仅在配合 `--provider mock` 时才会同时使用 mock 抓取器（不联网）。

## 抓取器

搜索返回 URL 后，内置 `HttpFetcher` 会：

- 以 `fetch_concurrency`（默认 4）并发抓取，单页超时 `fetch_timeout`（默认 20s）；
- 跳过非 HTML 内容（PDF、图片等标记为失败，不中断流程）；
- 用标准库 `html.parser` 去除脚本/导航/页眉页脚等噪声，优先 `<article>`/`<main>`；
- 正文截断到 `fetch_max_chars`（默认 12000 字符），结果缓存 `cache_ttl_hours`（默认 24h）。

可调项见 [configuration.md](configuration.md#抓取与正文提取)。内置 User-Agent 会带上项目地址，
方便站点管理员识别来源；如需替换可设置 `DEEPRESEARCH_USER_AGENT`。

## 安全提示

- **key 只放在环境变量或 `.env`**：`.env` 已 gitignore；不要提交、不要贴到 issue/截图/日志。
  `deepresearch providers` 与 `/api/config` 的 key 展示是**掩码**，但仍建议谨慎截图。
- key 泄露后立即在服务商后台吊销并重新生成；检查 CI/Actions Secrets 是否误写进 workflow。
- Docker 部署用 `--env-file`/environment 注入，**不要 `COPY .env`** 进镜像（会写进镜像层历史）。
- 抓取目标来自第三方搜索结果，可能包含恶意内容；工具不执行 JavaScript、限制响应大小，
  但**不要在生产网络以高权限运行**，详见 [SECURITY.md](../SECURITY.md)。
- 遵守各服务商的条款与限流；批量高频调用可能被限流甚至封号，本项目会重试 429，但不会绕过限制。

## 常见问题排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `配置错误：... needs an API key` | 选了真实 provider 但没配 key | 填对应 key，或改用 `--demo` |
| HTTP 401 / 403 | key 无效、过期、无权限 | 重新生成 key；确认服务商与 base_url 匹配 |
| HTTP 404 `.../chat/completions` | `llm_base_url` 少了 `/v1` 或路径不对 | 端点一般以 `/v1` 结尾；核对服务商文档 |
| HTTP 429 | 限流/额度不足 | 等待重试、降 depth、充值或换 key |
| `connection refused` | Ollama / vLLM / SearXNG 未启动或端口不对 | 确认服务监听地址，容器内用 `host.docker.internal` 访问宿主 |
| 搜索 400/403 | SearXNG 未开启 json 格式或被 limiter 拦截 | 修改 `settings.yml`，放行来源 |
| 搜索结果为空 | query 太窄、key 无效、网络受限 | 换 provider 或用更宽泛的问题；`--search none` 兜底 |
| 报告里没有参考文献 | 搜索为 `none` 或全部抓取失败 | 检查搜索配置与网络；看 `trace.jsonl` 中的 warning |
| 输出 JSON 解析失败 | 模型不遵循 JSON 输出 | 换更强模型；流水线会自动重试并兜底，但质量下降 |
