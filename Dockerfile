# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# DeepResearch —— 零第三方运行时依赖（Python 标准库），镜像很小。
#
#   docker build -t deepresearch:0.1.0 .
#   docker run --rm -p 127.0.0.1:8000:8000 deepresearch:0.1.0
#   # 离线 mock 演示（无需任何 key）
#   docker run --rm -it deepresearch:0.1.0 \
#       deepresearch run "固态电池 2025 产业化进展" --provider mock
#   # 接真实服务：通过环境变量或 env-file 注入 key（不要烘焙进镜像）
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env deepresearch:0.1.0
# -----------------------------------------------------------------------------
FROM python:3.12-slim

# 容器内行为：不写 .pyc、输出不缓冲（SSE 日志即时刷新）、不缓存 wheel
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先只复制构建所需文件，最大化层缓存
COPY pyproject.toml README.md ./
COPY src ./src

# 只有标准库运行时依赖；这里安装的只是本项目自身
RUN pip install --no-cache-dir .

# 非 root 运行（固定 uid/gid，方便挂载卷授权）
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --shell /usr/sbin/nologin --create-home app \
    && mkdir -p /data/reports /data/cache \
    && chown -R app:app /data /app

# 运行时数据目录：报告与缓存都放在可挂载的 /data 下
ENV DEEPRESEARCH_OUT_DIR=/data/reports \
    DEEPRESEARCH_CACHE_DIR=/data/cache

USER app

EXPOSE 8000

# 健康检查走内置 /api/health（纯标准库请求）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# 默认启动 Web UI（监听容器内所有网卡，端口映射请绑定到 127.0.0.1）
CMD ["deepresearch", "serve", "--host", "0.0.0.0", "--port", "8000"]
