# 配置

DeepResearch 的所有可调项集中在一处：`Settings`（`src/deepresearch/config.py`）。
可以用**环境变量**、**`.env` 文件**或 **CLI 参数**设置，三者优先级明确。

- 首次使用请看 [quickstart.md](quickstart.md)
- 各 provider 的申请与接入步骤见 [providers.md](providers.md)

## 配置优先级

从高到低：

1. **CLI 参数**（如 `--depth deep`、`--provider deepseek`）
2. **真实环境变量**（如 `export DEEPRESEARCH_DEPTH=deep`）
3. **`.env` 文件**（默认读取当前目录 `.env`，可用全局参数 `--env-file PATH` 指定）
4. **内置默认值**（`Settings()` 的字段默认值）

> 全局参数 `--env-file` 必须写在子命令**之前**：
> `deepresearch --env-file .env.prod run "问题"`。
> provider 的 `llm_base_url` / `llm_model` 若未显式设置，会用所选预设的默认值补全。

## 三种配置方式

### 方式一：`.env` 文件（推荐）

```bash
cp .env.example .env              # macOS / Linux / Git Bash
Copy-Item .env.example .env       # Windows PowerShell
# 编辑 .env，至少填写 LLM key；接真实搜索时再填 TAVILY_API_KEY
```

仓库自带的 `.env.example` **默认等价于离线 mock 配置**（所有会触发联网的项都留空/注释），
复制后不修改也能跑通演示。也可以用命令生成另一份模板：

```bash
deepresearch init                 # 在当前目录生成 .env（内嵌中文注释）
deepresearch init --output .env.prod
deepresearch init --force         # 覆盖已存在的文件（否则返回码 1 并提示）
```

> 注意：`deepresearch init` 生成的模板预填了 `DEEPRESEARCH_LLM_PROVIDER=deepseek` 与
> `TAVILY_API_KEY=tvly-your-key-here` 占位值，**需要替换成真实 key 才能联网运行**；
> 想离线体验请用 `--demo`（或把两项都改成 `mock`）。

### 方式二：环境变量

```bash
# macOS / Linux / Git Bash
export DEEPSEEK_API_KEY=sk-...
export TAVILY_API_KEY=tvly-...

# Windows PowerShell（仅当前会话有效）
$env:DEEPSEEK_API_KEY = "sk-..."
$env:TAVILY_API_KEY = "tvly-..."
```

也可以永久设置（Linux 写入 `~/.bashrc`；Windows 用「系统属性 → 环境变量」）。

### 方式三：CLI 参数

临时覆盖，不改任何文件：

```bash
deepresearch run "问题" --depth deep --search tavily --lang zh
deepresearch run "问题" --provider ollama --model qwen2.5:7b --search none
deepresearch run "问题" --demo          # 强制 mock LLM + mock 搜索（离线）
```

## LLM provider 预设

| provider | 默认端点 `llm_base_url` | 默认模型 `llm_model` | 密钥变量 | 说明 |
| --- | --- | --- | --- | --- |
| `deepseek` | `https://api.deepseek.com/v1` | `deepseek-chat` | `DEEPSEEK_API_KEY` | 性价比高，中文表现好 |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` | `OPENAI_API_KEY` | 通用 |
| `openrouter` | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | `OPENROUTER_API_KEY` | 一个 key 访问多家模型 |
| `ollama` | `http://localhost:11434/v1` | `qwen2.5:7b` | 无需密钥 | 本地模型 |
| `custom` | （必须显式设置） | （必须显式设置） | `LLM_API_KEY` 或 `DEEPRESEARCH_LLM_API_KEY` | 任意 OpenAI 兼容端点（vLLM、LM Studio、网关等） |
| `mock` | （不联网） | `mock-researcher` | 无需密钥 | 离线确定性演示/测试 |

## 环境变量总表

每个字段都有 `DEEPRESEARCH_<字段名大写>` 形式的环境变量。带「别名」的字段还接受常见厂商变量。

### LLM

| 环境变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DEEPRESEARCH_LLM_PROVIDER` | str | 见下文[自动检测](#provider-自动检测) | `deepseek` / `openai` / `openrouter` / `ollama` / `custom` / `mock` |
| `DEEPRESEARCH_LLM_MODEL` | str | 预设默认 | 模型名；别名：`LLM_MODEL`、`OPENAI_MODEL`、`DEEPSEEK_MODEL` |
| `DEEPRESEARCH_LLM_API_KEY` | str | 空 | API key；别名：`LLM_API_KEY`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`OPENROUTER_API_KEY` |
| `DEEPRESEARCH_LLM_BASE_URL` | str | 预设默认 | OpenAI 兼容端点（含 `/v1`）；别名：`LLM_BASE_URL`、`OPENAI_BASE_URL`、`DEEPSEEK_BASE_URL` |
| `DEEPRESEARCH_LLM_TEMPERATURE` | float | `0.3` | 采样温度 |
| `DEEPRESEARCH_LLM_MAX_TOKENS` | int | `0` | 单次回复上限；`0` = 服务端默认 |
| `DEEPRESEARCH_LLM_TIMEOUT` | float | `120` | 单次 LLM 请求超时（秒） |
| `DEEPRESEARCH_LLM_MAX_RETRIES` | int | `2` | 429/5xx/网络错误重试次数 |

### 联网搜索

| 环境变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DEEPRESEARCH_SEARCH_PROVIDER` | str | 见下文[自动检测](#provider-自动检测) | `tavily` / `searxng` / `none` / `mock` |
| `DEEPRESEARCH_TAVILY_API_KEY` | str | 空 | Tavily key；别名 `TAVILY_API_KEY` |
| `DEEPRESEARCH_TAVILY_SEARCH_DEPTH` | str | `basic` | `basic`（快、便宜）/ `advanced`（更全、更慢贵） |
| `DEEPRESEARCH_SEARXNG_URL` | str | 空 | 自建 SearXNG 地址；别名 `SEARXNG_URL`（需开启 `format=json`） |
| `DEEPRESEARCH_SEARCH_MAX_RESULTS` | int | `6` | 每条 query 返回结果数，自动限制在 1–20 |
| `DEEPRESEARCH_SEARCH_RECENCY_DAYS` | int | `0` | `0` = 不限时间；`>0` 只取最近 N 天 |
| `DEEPRESEARCH_SEARCH_TIMEOUT` | float | `20` | 搜索请求超时（秒） |
| `DEEPRESEARCH_SEARCH_MAX_RETRIES` | int | `1` | 搜索请求重试次数 |

### 抓取与正文提取

| 环境变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DEEPRESEARCH_FETCH_TIMEOUT` | float | `20` | 单页抓取超时（秒） |
| `DEEPRESEARCH_FETCH_MAX_CHARS` | int | `12000` | 单页正文最多保留字符数 |
| `DEEPRESEARCH_FETCH_CONCURRENCY` | int | `4` | 并发抓取数，自动限制在 1–16 |
| `DEEPRESEARCH_FETCH_MIN_CHARS` | int | `300` | 正文少于此值视为质量不足（回退策略） |
| `DEEPRESEARCH_USER_AGENT` | str | 空 | 自定义 User-Agent；留空使用内置 UA（含项目地址，便于站长识别） |
| `DEEPRESEARCH_CACHE_DIR` | str | `.deepresearch/cache` | 网页缓存目录 |
| `DEEPRESEARCH_CACHE_TTL_HOURS` | float | `24` | 缓存有效期；`<=0` 等价禁用 |
| `DEEPRESEARCH_USE_CACHE` | bool | `true` | 是否启用网页缓存 |

### 调研行为

| 环境变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DEEPRESEARCH_LANGUAGE` | str | `zh` | `zh` / `en`；别名 `DEEPRESEARCH_LANG`（`en*` 视为英文，其余为中文） |
| `DEEPRESEARCH_DEPTH` | str | `standard` | `quick` / `standard` / `deep`，见[深度预设](#深度预设) |
| `DEEPRESEARCH_OUT_DIR` | str | `reports` | 报告输出目录；每次运行创建一个子目录 |
| `DEEPRESEARCH_MAX_SOURCES` | int | `0` | 来源硬上限；`0` = 使用深度预设（8/14/24） |
| `DEEPRESEARCH_MAX_LLM_CALLS` | int | `0` | LLM 调用次数预算；`0` = 不限（仅环境变量可设，无对应 CLI 参数） |
| `DEEPRESEARCH_MAX_COST_USD` | float | `0` | 预估费用预算（美元）；`0` = 不限 |
| `DEEPRESEARCH_MAX_SECONDS` | float | `0` | 墙钟时间预算（秒）；`0` = 不限 |
| `DEEPRESEARCH_REPORT_JSON` | bool | `true` | 是否写 `result.json`（CLI 用 `--no-json` 关闭） |
| `DEEPRESEARCH_REPORT_TRACE` | bool | `true` | 是否写 `trace.jsonl`（CLI 用 `--no-trace` 关闭） |

### 其他

| 环境变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DEEPRESEARCH_LOG_LEVEL` | str | `info` | `debug` / `info` / `warn` / `error` / `quiet` |

布尔值接受 `1/true/yes/on` 与 `0/false/no/off`（大小写不敏感）。
数值型环境变量写非法值会直接报配置错误。

## provider 自动检测

未显式设置 `DEEPRESEARCH_LLM_PROVIDER` 时：

1. 有 `DEEPSEEK_API_KEY` → `deepseek`
2. 否则有 `OPENAI_API_KEY` → `openai`
3. 否则有 `OPENROUTER_API_KEY` → `openrouter`
4. 都没有 → `mock`（离线）

未显式设置 `DEEPRESEARCH_SEARCH_PROVIDER` 时：

1. 有 `TAVILY_API_KEY` → `tavily`
2. 否则有 `SEARXNG_URL` → `searxng`
3. 否则 LLM 为 `mock` → `mock`
4. 否则 → `none`（只用模型知识，无外部引用）

所以最常见的配置就是**只填 key**：`DEEPSEEK_API_KEY` + `TAVILY_API_KEY`，其余全自动。

## CLI 参数 ↔ 配置

| CLI 参数 | 等价设置 | 作用 |
| --- | --- | --- |
| `--depth quick\|standard\|deep` | `DEEPRESEARCH_DEPTH` | 调研深度 |
| `--lang zh\|en` | `DEEPRESEARCH_LANGUAGE` | 报告语言 |
| `--provider ...` | `DEEPRESEARCH_LLM_PROVIDER` | LLM 提供方 |
| `--model NAME` | `DEEPRESEARCH_LLM_MODEL` | 模型名 |
| `--base-url URL` | `DEEPRESEARCH_LLM_BASE_URL` | 自定义端点 |
| `--search ...` | `DEEPRESEARCH_SEARCH_PROVIDER` | 搜索后端 |
| `--out DIR` | `DEEPRESEARCH_OUT_DIR` | 输出目录 |
| `--max-sources N` | `DEEPRESEARCH_MAX_SOURCES` | 来源上限 |
| `--max-cost USD` | `DEEPRESEARCH_MAX_COST_USD` | 费用预算 |
| `--max-seconds SEC` | `DEEPRESEARCH_MAX_SECONDS` | 时间预算 |
| `--no-json` / `--no-trace` | `DEEPRESEARCH_REPORT_JSON` / `_TRACE` | 关闭附加产物 |
| `--no-save` | （仅 CLI） | 不落盘 |
| `--stdout` | （仅 CLI） | 只输出 Markdown，适合管道 |
| `--quiet` / `-q` | （仅 CLI） | 隐藏实时进度，只留最终摘要 |
| `--demo` | （仅 CLI） | 强制 mock LLM + mock 搜索，离线演示 |
| `--env-file PATH` | （仅 CLI，全局） | 指定 `.env` 文件，必须在子命令前 |

## `.env` 文件语法

由内置解析器处理（不依赖 python-dotenv）：

```dotenv
# 注释以 # 开头
DEEPRESEARCH_DEPTH=deep
TAVILY_API_KEY="tvly-abc123"          # 引号会被去掉
export DEEPSEEK_API_KEY=sk-xyz        # 可选的 export 前缀
DEEPRESEARCH_OUT_DIR=${HOME}/reports  # ${VAR} / ${VAR:-default} 用真实环境变量展开
```

- 未加引号的值中，` #` 之后视为行内注释。
- 真实环境变量优先于 `.env` 中的同名项。
- `.env` 已在 `.gitignore` 中，**不要提交真实密钥**。

## 校验与告警

启动前会调用 `Settings.validate()`：

**致命错误**（抛 `ConfigError`，CLI 返回码 2）：

- 使用 `deepseek/openai/openrouter/custom` 但没有 API key（`ollama` 与 `mock` 不需要）；
- `provider=custom` 但没有 `llm_base_url`；
- `llm_base_url` 不是 `http(s)://` 开头；
- 搜索用 `tavily` 但没有 key；用 `searxng` 但没有 URL；
- `llm_provider` 或 `depth` 取值非法。

**非致命告警**（继续运行，打印 warning）：

- 搜索为 `none`：报告只依赖模型知识，没有外部引用；
- LLM 为 `mock`：报告是确定性演示，不是真实调研；
- 缓存被禁用：每次都会重新抓取网页。

## 深度预设

| depth | 子问题 | 每问题 query | 来源上限 | 反思轮数 | finding 上限 | 每节目标词数 | 适用场景 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `quick` | 3 | 2 | 8 | 1 | 6 | 180 | 快速摸底、概念解释 |
| `standard` | 5 | 3 | 14 | 2 | 14 | 320 | 默认，行业/技术综述 |
| `deep` | 7 | 4 | 24 | 3 | 24 | 550 | 深度报告、争议话题 |

`DEEPRESEARCH_MAX_SOURCES` 会**替换**深度预设的来源上限（只要设置非 0 即覆盖，不是取较小值），
CLI 的 `--max-sources N` 等价。

## 费用估算

费用只用于**预算控制与结果展示**，不等于服务商实际账单。估算方式：
`prompt_tokens × 输入价 + completion_tokens × 输出价`（每 100 万 token 的美元价格），
价目表内置在 `config.MODEL_PRICING`：

| 模型 | 输入（$/1M tokens） | 输出（$/1M tokens） |
| --- | --- | --- |
| `deepseek-chat` | 0.27 | 1.10 |
| `deepseek-reasoner` | 0.55 | 2.19 |
| `gpt-4o-mini` | 0.15 | 0.60 |
| `gpt-4o` | 2.50 | 10.00 |
| `gpt-4.1-mini` | 0.40 | 1.60 |
| `claude-3-5-haiku` | 0.80 | 4.00 |
| `mock-researcher` | 0 | 0 |

- 价目表**会过时**：价格调整后请以服务商官网为准；本项目只把它当相对预算参考。
- 不在表中的模型按 0 计算（费用显示为 0），但仍可用 `--max-seconds` / `--max-llm-calls` 限制消耗。
- 一次 `standard` 运行通常包含十几次到几十次 LLM 调用，实际成本取决于模型与报告长度；
  建议首次运行加 `--max-cost 0.10` 之类的保护。
- 搜索（Tavily 等）的费用不在本估算内，请按服务商计费规则自行考虑。

## 常见配置示例

### 1. 完全离线（无 key）

```dotenv
DEEPRESEARCH_LLM_PROVIDER=mock
DEEPRESEARCH_SEARCH_PROVIDER=mock
DEEPRESEARCH_DEPTH=quick
```

### 2. DeepSeek + Tavily（推荐的真实调研组合）

```dotenv
DEEPSEEK_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
DEEPRESEARCH_DEPTH=standard
DEEPRESEARCH_LANGUAGE=zh
```

### 3. 本地 Ollama + 自建 SearXNG（全内网）

```dotenv
DEEPRESEARCH_LLM_PROVIDER=ollama
DEEPRESEARCH_LLM_BASE_URL=http://localhost:11434/v1
DEEPRESEARCH_LLM_MODEL=qwen2.5:7b
DEEPRESEARCH_SEARCH_PROVIDER=searxng
SEARXNG_URL=http://localhost:8080
DEEPRESEARCH_MAX_SECONDS=600
```

### 4. 任意 OpenAI 兼容网关（vLLM / LM Studio / 公司网关）

```dotenv
DEEPRESEARCH_LLM_PROVIDER=custom
DEEPRESEARCH_LLM_BASE_URL=https://llm-gateway.internal/v1
DEEPRESEARCH_LLM_API_KEY=...
DEEPRESEARCH_LLM_MODEL=my-model
DEEPRESEARCH_SEARCH_PROVIDER=none
```

### 5. 严格预算

```bash
deepresearch run "问题" --max-cost 0.05 --max-seconds 180 --max-sources 8 --depth standard
```

### 6. Docker 部署

```bash
cp .env.example .env      # 填 key（容器不会读取仓库外的文件）
docker compose up --build
```

容器内的报告与缓存目录固定为 `/data/reports`、`/data/cache`（见 Dockerfile 与
[docker-compose.yml](../docker-compose.yml)），可通过卷映射持久化。

## 相关文件

- [`.env.example`](../.env.example) —— 全字段注释模板（默认即离线 mock）
- [providers.md](providers.md) —— 各服务商 key 申请步骤
- [faq.md](faq.md) —— 配置相关的常见问题
