# 安全策略

## 支持的版本

| 版本 | 是否接收安全修复 |
| --- | --- |
| 0.1.x | ✅ |
| < 0.1 | ❌ |

## 报告漏洞

**请勿通过公开 issue、PR 或讨论区报告安全漏洞。**

推荐渠道：

1. 在 GitHub 仓库页面进入 **Security → Advisories → Report a vulnerability**
   （私密安全公告），直接与维护者沟通；
2. 若仓库未启用该功能，请通过维护者 GitHub 主页所列的联系方式私信。

请在报告中包含：受影响版本、复现步骤或 PoC、影响评估、可能的修复思路（如已有）。
我们会在收到报告后尽快确认，并在修复发布后征得同意给予致谢。

## 本项目特有的安全关注点

DeepResearch 会**代表用户发起网络请求并调用第三方 API**，请特别注意：

### API key 安全

- `.env` 已加入 `.gitignore`，**不要把任何真实 key 提交到仓库**；只提交 `.env.example`。
- 不要把 key 写进 issue、日志、截图、报告正文或示例文件。
- 配置摘要（`/api/config`、`deepresearch providers`）会对 key 做掩码处理（仅保留首尾少量字符），
  但仍建议在分享截图前自行检查。
- CI 中如需真实 key，请使用 GitHub Actions Secrets，不要写在 workflow 文件里。
- key 泄露后请立即在服务商控制台**吊销并轮换**；Git 历史中的泄露需重写历史或视为已永久泄露。
- Docker / Compose 部署时通过环境变量或 `env_file` 注入 key，不要把 key 烘焙进镜像层
  （`COPY .env` 会把密钥写进镜像历史）。

### 网络抓取与 SSRF 风险

- 抓取目标是搜索结果返回的 URL，理论上可能指向内网地址。默认顺序是「先搜索、再抓取」，
  但**不要在生产网络中以高权限身份运行本工具**；建议在隔离网络或容器中运行，并限制出站访问。
- 抓取器只读取 HTTP(S)、限制响应大小（`fetch_max_chars` / 内部字节上限）、不执行 JavaScript，
  但不对第三方内容做可信性背书：**报告内容可能包含恶意或错误信息，引用前请自行核实。**

### Web 服务

- `deepresearch serve` 默认只绑定 `127.0.0.1`，**没有身份认证**，也没有 CSRF/速率限制。
- 不要把它直接暴露在公网；如需共享，请放在带认证的反向代理之后，并只允许可信用户访问。
- 服务会把运行记录写入输出目录（默认 `reports/`），其中包含研究问题与报告正文，注意访问权限。

### 第三方内容与许可证

- 报告会引用并摘录第三方网页内容，转载/商用前请自行确认来源的版权与使用条款。
- 本项目以 MIT 许可发布，见 [LICENSE](LICENSE)。

## 依赖与供应链

- 运行时**零第三方依赖**，只使用 Python 标准库，攻击面因此显著减小。
- 开发依赖（ruff / build / twine 等）仅用于本地与 CI，通过 Dependabot 跟踪更新。
- 如发现本项目代码或其发布产物（sdist/wheel/Docker 镜像）被篡改，请按上述私密渠道报告。

## 安全的相关文档

- 配置与密钥管理：[docs/configuration.md](docs/configuration.md)
- Provider 与密钥申请：[docs/providers.md](docs/providers.md)
