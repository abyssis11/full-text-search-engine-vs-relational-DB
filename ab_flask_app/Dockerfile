FROM python:3.7-slim-buster

RUN apt-get update && apt-get install -y apache2-utils

WORKDIR /app

COPY requirements.txt ./

RUN pip install -r requirements.txt

COPY . .

EXPOSE 4001

CMD [ "flask", "run", "--host=0.0.0.0", "--port=4001"]