FROM node:18-alpine as webui                                                                                                                                             
COPY . /app                 
WORKDIR /app/fcb-fronted/                                                                                                                                                               
ENV NPM_CONFIG_LOGLEVEL=verbose
RUN npm i
RUN npm run build-only
RUN mv dist/logo_small.png dist/assets/


FROM python:3.9.5-alpine as FileCodeBox
LABEL author="Lan"
LABEL email="vast@tom.com"
LABEL version="6"


# 先安装依赖可以产生缓存
WORKDIR /app
COPY requirements.txt /app
# 安装gcc
RUN apk add --no-cache gcc musl-dev
RUN /usr/local/bin/python -m pip install --upgrade pip && pip install -r requirements.txt
COPY ./backend/ /app
COPY --from=webui /app/fcb-fronted/dist/ /app/dist
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN echo 'Asia/Shanghai' >/etc/timezone
EXPOSE 12345
CMD ["python","main.py"]