FROM python:3.9.5-slim-buster
LABEL author="Lan"
LABEL email="xzu@live.com"

# 将当前目录下的文件复制到容器的 /app 目录
COPY . /app

# 设置时区为亚洲/上海
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone

# 设置工作目录
WORKDIR /app

# 删除不必要的目录，减少镜像体积
RUN rm -rf docs fcb-fronted

# 安装依赖
RUN pip install -r requirements.txt

# 暴露端口
EXPOSE 12345

# 启动应用
CMD ["python", "main.py"]