FROM python:3.11-slim
LABEL author="Lan"
LABEL email="xzu@live.com"

# 设置工作目录
WORKDIR /app

# 仅拷贝依赖文件以利用缓存
COPY requirements.txt /app/requirements.txt

# 设置时区 + 安装编译依赖 + 升级 pip + 安装依赖（含从源码编译的回退）+ 清理构建依赖
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone && \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        pkg-config \
        libssl-dev \
        rustc \
        cargo && \
    python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove build-essential rustc cargo && \
    rm -rf /var/lib/apt/lists/*

# 拷贝源码
COPY . /app

# 删除不必要的目录，减少镜像体积
RUN rm -rf docs fcb-fronted

# 暴露端口
EXPOSE 12345

# 启动应用
CMD ["python", "main.py"]