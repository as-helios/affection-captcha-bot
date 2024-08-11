FROM python:3.12
RUN apt update
RUN apt upgrade -y
RUN apt install -y build-essential libtiff5-dev libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev tcl8.6-dev tk8.6-dev python3-tk
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["sh", "-c", "python main.py"]
