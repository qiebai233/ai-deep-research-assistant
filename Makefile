# =============================================================================
# DeepResearch —— 常用开发/构建/运行命令
#
# 需要 GNU Make：
#   - macOS / Linux：系统自带或 `brew install make`
#   - Windows：建议在 Git Bash / WSL 里运行，或安装
#     https://github.com/mbuilov/gnumake-windows 后使用 `make`
#     （Windows 没有 make 时，请直接复制下面各目标里的命令到 PowerShell 执行，
#      例如 `python run_tests.py`、`python -m build`、`docker build -t deepresearch:0.1.0 .`）
#
# 约定：
#   PY     解释器（可覆盖：`make test PY=py`）
#   DR     CLI 入口（默认依赖 `make install`/`make dev` 安装的 deepresearch 命令）
# =============================================================================

PY ?= python
DR ?= deepresearch
Q  ?= 固态电池 2025 产业化进展与挑战
VERSION := 0.1.0
IMAGE ?= deepresearch:$(VERSION)

.DEFAULT_GOAL := help

.PHONY: help install dev test lint fmt build clean run demo serve providers docker docker-run docker-stop publish-check

help: ## 显示所有可用目标
	@echo "DeepResearch $(VERSION) —— 常用命令"
	@echo ""
	@echo "  make install      以可编辑模式安装（pip install -e .）"
	@echo "  make dev          安装开发依赖（ruff/build/twine 等）"
	@echo "  make test         运行全量测试（python run_tests.py）"
	@echo "  make lint         ruff 静态检查（src + tests）"
	@echo "  make fmt          ruff 自动修复"
	@echo "  make build        构建 sdist + wheel（dist/）"
	@echo "  make clean        清理构建/缓存产物"
	@echo "  make run          真实调研（需已配置 LLM/搜索）"
	@echo "  make demo         离线 mock 演示（无需任何 key）"
	@echo "  make serve        启动 Web UI（http://127.0.0.1:8000）"
	@echo "  make providers    打印当前 provider 配置"
	@echo "  make docker       构建 Docker 镜像 $(IMAGE)"
	@echo "  make docker-run   以 Compose 启动服务"
	@echo ""
	@echo "变量：Q=\"研究问题\" PY=$(PY) DR=$(DR)"

install: ## 可编辑安装
	$(PY) -m pip install -e .

dev: ## 安装开发依赖
	$(PY) -m pip install -e ".[dev]"

test: ## 全量测试（无需安装）
	$(PY) run_tests.py

lint: ## ruff 检查
	$(PY) -m ruff check src tests

fmt: ## ruff 自动修复
	$(PY) -m ruff check --fix src tests

build: clean ## 构建 sdist + wheel
	$(PY) -m build

clean: ## 清理构建与缓存
	$(PY) -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['build','dist','src/deepresearch.egg-info','.pytest_cache','.ruff_cache','.coverage','htmlcov']]"
	$(PY) -c "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"

run: ## 真实调研（需 API key）
	$(DR) run "$(Q)"

demo: ## 离线 mock 演示（无需 key、不联网）
	$(DR) run "$(Q)" --provider mock --depth standard

serve: ## 启动 Web UI 并打开浏览器
	$(DR) serve --open

providers: ## 查看当前 provider 配置
	$(DR) providers

docker: ## 构建 Docker 镜像
	docker build -t $(IMAGE) .

docker-run: ## 通过 compose 启动（需要 Docker Compose v2.24+）
	docker compose up --build -d

docker-stop: ## 停止 compose 服务
	docker compose down

publish-check: lint test build ## 发布前自检：lint + test + build
	@echo "✓ 发布自检通过，产物在 dist/"
