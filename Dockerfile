FROM python:3.9.5
LABEL author="Lan"
LABEL email="vast@tom.com"
LABEL version="1.5.4"


COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 12345
CMD ["python","main.py"]