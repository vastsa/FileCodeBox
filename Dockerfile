FROM python:3.9.5-slim-buster
LABEL author="Lan"
LABEL email="vast@tom.com"

COPY . /app
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN echo 'Asia/Shanghai' >/etc/timezone
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 12345
CMD ["python","main.py"]