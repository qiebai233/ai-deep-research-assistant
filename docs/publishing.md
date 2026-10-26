# 发布与发行

本文面向维护者：如何把本仓库发布到 GitHub、打 tag、生成 Release，以及可选的 PyPI 发布。
日常使用请看 [quickstart.md](quickstart.md)。

## 0. 前提

| 工具 | 用途 | 检查 |
| --- | --- | --- |
| Git | 版本管理、推送 | `git --version` |
| GitHub CLI `gh` | 一键建仓（可选） | `gh --version`、`gh auth status` |
| Python ≥ 3.10 | 构建 sdist/wheel | `python --version` |
| Docker（可选） | 构建镜像 | `docker --version` |

首次使用 `gh` 需要登录：`gh auth login`（选择 HTTPS + 浏览器授权，需 `repo` 权限）。

## 1. 一键发行（推荐）

脚本会完成：检查环境 → 替换占位符 → 提交 → 建仓并推送 → 打 tag → 提示后续步骤。

### Windows（PowerShell）

```powershell
# 先预览将执行的动作与将被修改的文件（不会真的改动）
.\scripts\publish.ps1 -Owner qiebai233 -DryRun

# 正式发行
.\scripts\publish.ps1 -Owner qiebai233
```

若 PowerShell 执行策略阻止脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish.ps1 -Owner qiebai233
```

### macOS / Linux

```bash
chmod +x scripts/publish.sh

./scripts/publish.sh --owner qiebai233 --dry-run   # 预览
./scripts/publish.sh --owner qiebai233             # 正式发行
```

### 脚本做了什么

1. 检查 `git` 是否存在；不存在则打印手动命令并以 0 退出（不会假装成功）。
2. 检查工作区是否干净（`git status --porcelain`），有未提交改动时停止并提示。
3. **替换占位符** `qiebai233` → `-Owner` 的值，范围：
   `README.md`、`README_EN.md`、`docs/**`、`.github/**`、`pyproject.toml`、`CHANGELOG.md`、
   `CONTRIBUTING.md`、`SECURITY.md`、`examples/**`，以及源码中的文档链接与 User-Agent
   （`src/deepresearch/cli.py`、`src/deepresearch/http.py`）。
4. `git init`（若尚未初始化）；`git add -A`；
   提交信息为 `release: v0.1.0`（已有同名提交或无改动时跳过）。
5. `gh repo create <owner>/deepresearch --public --source . --push`；
   未安装 `gh` 时打印等价的手动命令并退出 0，不阻断流程。
6. `git tag v0.1.0` 并推送 `main` 与 tag。
7. 打印 Actions 与 Release 页面链接（`https://github.com/<owner>/deepresearch/actions` 等）。

> 脚本**不会**替你创建 GitHub Release：推送 tag 后由
> [`.github/workflows/release.yml`](../.github/workflows/release.yml) 自动构建并发布。

### 脚本参数

| 参数 | PS1 | SH | 说明 |
| --- | --- | --- | --- |
| 仓库所有者 | `-Owner <name>` | `--owner <name>` | 必填，GitHub 用户名或组织名 |
| 演练模式 | `-DryRun` | `--dry-run` | 只打印计划，不写文件/不执行 git 写操作 |
| 跳过占位符替换 | `-SkipReplace` | `--skip-replace` | 已完成替换时使用 |
| 跳过建仓 | `-SkipCreate` | `--skip-create` | 仓库已存在于 GitHub，只推送 |
| 自定义 tag | `-Tag v0.1.1` | `--tag v0.1.1` | 默认 `v0.1.0` |

## 2. 手动发行

### 2.1 初始化并推送

```bash
# 在仓库根目录
git init -b main
git add -A
git commit -m "release: v0.1.0"

# 方式 A：使用 gh
gh repo create <owner>/deepresearch --public --source . --push

# 方式 B：先建空仓库，再关联
git remote add origin https://github.com/<owner>/deepresearch.git
git branch -M main
git push -u origin main
```

### 2.2 替换占位符

```bash
grep -rl "qiebai233" . --exclude-dir=.git

# Linux/macOS
grep -rl "qiebai233" . --exclude-dir=.git | xargs sed -i "s/qiebai233/<owner>/g"

# Windows PowerShell（先列出来确认，再替换）
Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '\\\.git\\' } |
  Select-String -Pattern 'qiebai233' | Select-Object -ExpandProperty Path -Unique
```

替换后重新检查：`grep -rn "qiebai233" . --exclude-dir=.git` 应无输出（`docs/publishing.md`
本身可能保留示例，可接受）。然后提交：

```bash
git add -A && git commit -m "chore: point links at <owner>/deepresearch"
```

### 2.3 打 tag 并推送

```bash
git tag -a v0.1.0 -m "DeepResearch v0.1.0"
git push -u origin main
git push origin v0.1.0
```

推送 tag 后，Actions 中的 **Release** 工作流会自动：

1. 校验 tag 与 `src/deepresearch/__init__.py` 的 `__version__` 是否一致（不一致直接失败）；
2. 跑全量测试；
3. `python -m build` 生成 sdist + wheel，并生成 `SHA256SUMS.txt`；
4. 创建 GitHub Release，附上三个文件，并用 GitHub 自动生成 release notes。

## 3. 版本号规则

语义化版本 `MAJOR.MINOR.PATCH`，tag 带 `v` 前缀（`v0.1.0`）。发版时**三处必须一致**：

| 位置 | 内容 |
| --- | --- |
| `pyproject.toml` | `version = "0.1.0"` |
| `src/deepresearch/__init__.py` | `__version__ = "0.1.0"` |
| Git tag | `v0.1.0` |

另外更新 `CHANGELOG.md`：把 `[Unreleased]` 的内容整理到新的 `## [0.1.0] - YYYY-MM-DD` 小节，
并更新底部比较链接。

发布前自检：

```bash
python -m compileall -q src
ruff check src tests
python run_tests.py
python -m build
python -m twine check dist/*        # 需要 dev 依赖
```

## 4. 发布前检查清单

- [ ] 全量测试通过（`python run_tests.py`），ruff 无告警
- [ ] `python -m build` 成功，`dist/` 含 `.whl` 与 `.tar.gz`
- [ ] 三处版本号一致，`CHANGELOG.md` 已更新
- [ ] `qiebai233` 占位符已全部替换（badges、链接、`pyproject.toml` URLs、源码 User-Agent）
- [ ] README / docs 中的命令在干净环境中实际跑过（至少 `--demo` 全流程）
- [ ] `examples/sample_report.md` 是最新 mock 运行产物
- [ ] 截图/图（如 `assets/`）为最新 UI，且不含任何密钥
- [ ] `LICENSE` 年份与版权方正确
- [ ] 仓库已开启 Actions；`Settings → Actions → General` 允许工作流运行
- [ ] 如需 PyPI，已按第 6 节配置 trusted publishing

## 5. Release 工作流说明

见 [`.github/workflows/release.yml`](../.github/workflows/release.yml)：

- 触发：`push` 到 `v*` tag（`v0.1.0`、`v0.2.0-rc1` 等）；含 `-rc`/`-beta` 的 tag 会自动标记为 prerelease。
- `build` job：全历史 checkout → 校验版本 → 测试 → 构建 → 生成校验和 → 上传 artifact。
- `release` job：下载 artifact，用 `softprops/action-gh-release` 创建 Release 并附
  `*.whl`、`*.tar.gz`、`SHA256SUMS.txt`。
- 安装最新版：

```bash
pip install https://github.com/<owner>/deepresearch/releases/latest/download/deepresearch-0.1.0-py3-none-any.whl
```

（实际文件名以下载页为准。）

### 重试 / 撤回

- 工作流失败：修复后删除并重新打 tag：

```bash
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0
git tag -a v0.1.0 -m "DeepResearch v0.1.0"
git push origin v0.1.0
```

- 撤回 Release：在 GitHub Release 页面删除即可（**不要**删除 tag，除非也要撤销该版本）。

## 6. PyPI 发布（可选，默认关闭）

本项目默认只发 GitHub Release。要同时发 PyPI，推荐 Trusted Publishing（无需在仓库存 token）：

1. 在 <https://pypi.org/manage/account/publishing/> 添加 pending publisher：
   - PyPI Project Name：`deepresearch`
   - Owner：你的 GitHub 用户名
   - Repository name：`deepresearch`
   - Workflow name：`release.yml`
   - Environment name：`pypi`
2. 在 GitHub 仓库 **Settings → Environments** 新建环境 `pypi`（建议加 required reviewers）。
3. 编辑 `.github/workflows/release.yml`：
   - 取消注释文件末尾的 `publish-pypi` job；
   - 顶层 `permissions` 增加 `id-token: write`。
4. 打 tag 后会自动上传。若包名在 PyPI 已被占用，需先改 `pyproject.toml` 的 `name`。

也可手动发布：

```bash
pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*        # 需要 PyPI API token
```

## 7. Docker 镜像（可选）

仓库没有自动推送镜像到注册表；需要时手动构建并推送：

```bash
docker build -t deepresearch:0.1.0 .
docker tag deepresearch:0.1.0 ghcr.io/<owner>/deepresearch:0.1.0
echo "$GITHUB_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker push ghcr.io/<owner>/deepresearch:0.1.0
```

## 8. 部署到服务器（简介）

- **单机**：`docker compose up -d`（报告与缓存通过卷持久化；默认仅本机可访问）。
- **反向代理**：把 `127.0.0.1:8000` 交给 Nginx/Caddy，配置 HTTPS 与访问认证。
- **不要**把无鉴权的 `--host 0.0.0.0:8000` 直接暴露到公网。
- 密钥通过环境变量/`env_file` 注入，不要写进镜像或提交到仓库。
- 生产环境建议限制出站网络（抓取目标来自第三方搜索结果），并定期清理 `reports/` 与缓存。

## 9. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `git: command not found` | 未安装 Git；脚本会打印手动命令并退出 0。安装后重试 |
| `gh: command not found` | 未安装 GitHub CLI；按脚本打印的命令手动建仓推送即可 |
| `gh auth status` 报未登录 | `gh auth login`，需要 `repo` 权限 |
| 工作区不干净 | 先提交或 `git stash`；脚本不会强制覆盖 |
| tag 已存在 | `git tag -d v0.1.0 && git push origin :refs/tags/v0.1.0` 后重打 |
| Release 工作流失败在版本校验 | tag 与 `__version__` 不一致，统一版本号后重打 tag |
| Actions 没有触发 | 仓库未启用 Actions，或 tag 不是以 `v` 开头 |
| Release 附件缺失 | 查看 `build` job 是否成功、`dist/` 是否为空 |
