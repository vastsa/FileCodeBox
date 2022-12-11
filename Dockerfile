FROM python:3.9.5
LABEL author="Lan"
LABEL email="vast@tom.com"
LABEL version="1.4.2"


COPY . /app
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN echo 'Asia/Shanghai' >/etc/timezone
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 12345
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "12345"]