# 第一阶段：构建前端主题
# 前端产物与 CPU 架构无关，使用原生构建平台避免在 QEMU 中运行 Node/pnpm。
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-builder

ARG FRONTEND_2024_REF=main
ARG FRONTEND_2023_REF=main

RUN apk add --no-cache git python3 make g++

RUN corepack enable && \
    corepack prepare pnpm@9.15.9 --activate

WORKDIR /build

# 克隆并构建固定版本的 2024 主题
RUN git clone --filter=blob:none --no-checkout https://github.com/vastsa/FileCodeBoxFronted.git /build/fronted-2024 && \
    cd /build/fronted-2024 && \
    git fetch --depth 1 origin "${FRONTEND_2024_REF}" && \
    git checkout --detach FETCH_HEAD && \
    pnpm install --frozen-lockfile --prod=false && \
    VITE_GIT_COMMIT="$(git rev-parse HEAD)" pnpm run build

# 克隆并构建固定版本的 2023 主题
RUN git clone --filter=blob:none --no-checkout https://github.com/vastsa/FileCodeBoxFronted2023.git /build/fronted-2023 && \
    cd /build/fronted-2023 && \
    git fetch --depth 1 origin "${FRONTEND_2023_REF}" && \
    git checkout --detach FETCH_HEAD && \
    npm install --legacy-peer-deps && \
    npm run build

# 第二阶段：构建最终镜像
FROM python:3.12-slim-bookworm
ARG APP_VERSION
ARG VCS_REF=unknown
ARG FRONTEND_2024_REF=main
ARG FRONTEND_2023_REF=main
LABEL author="Lan"
LABEL email="xzu@live.com"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.filecodebox.frontend-2024-revision="${FRONTEND_2024_REF}"
LABEL org.opencontainers.image.filecodebox.frontend-2023-revision="${FRONTEND_2023_REF}"

WORKDIR /app

# 复制项目文件（通过 .dockerignore 排除不必要的文件）
COPY . .

# 分支镜像使用带提交号的开发版本；正式镜像使用 VERSION 中的版本。
ENV APP_VERSION="${APP_VERSION}"

# 设置时区
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo 'Asia/Shanghai' > /etc/timezone

# 从构建阶段复制编译好的前端主题
COPY --from=frontend-builder /build/fronted-2024/dist ./themes/2024
COPY --from=frontend-builder /build/fronted-2023/dist ./themes/2023

# 安装系统安全更新 + Python 依赖
# 清理 apt 缓存，降低镜像噪音与扫描面
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r requirements.txt \
 && pip cache purge || true \
 && groupadd --system --gid 1000 appuser \
 && useradd --system --uid 1000 --gid appuser --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
 && mkdir -p /app/data \
 && chown -R appuser:appuser /app

# 非 root 运行，降低容器逃逸后的主机影响面
USER appuser

# 环境变量配置
ENV HOST="0.0.0.0" \
    PORT=12345 \
    WORKERS=1 \
    LOG_LEVEL="info" \
    FORWARDED_ALLOW_IPS=""

EXPOSE 12345

# 生产环境启动命令
# FORWARDED_ALLOW_IPS 默认为空：仅信任直连 IP，避免任意客户端伪造 X-Forwarded-*。
# 若前面有反向代理，请显式设置为代理网段，例如 "10.0.0.0/8,172.16.0.0/12"。
CMD ["sh", "-c", "exec uvicorn main:app --host \"$HOST\" --port \"$PORT\" --workers \"$WORKERS\" --log-level \"$LOG_LEVEL\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-}\""]
