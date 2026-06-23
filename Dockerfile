# 两阶段构建:前端 dist 拷进后端镜像,单容器运行
# === Stage 1: 前端构建 ===
FROM node:20-alpine AS frontend-builder
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY frontend/ ./
RUN pnpm build

# === Stage 2: Python 运行时 ===
FROM python:3.11-slim AS runtime
WORKDIR /app

# 安装 uv(快)
RUN pip install --no-cache-dir uv

# Backend deps
COPY README.md /README.md
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Backend code
COPY backend/app ./app
COPY tiers.yaml /app/tiers.yaml

# Frontend 静态产物
COPY --from=frontend-builder /build/dist ./static

ENV PYTHONPATH=/app
EXPOSE 3018
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3018"]
