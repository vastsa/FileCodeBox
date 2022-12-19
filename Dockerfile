FROM python:3.9.5-slim-buster
LABEL author="Lan"
LABEL email="vast@tom.com"
LABEL version="1.5.8"


COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 12345
CMD ["python","main.py"]