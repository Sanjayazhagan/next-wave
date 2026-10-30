FROM mcr.microsoft.com/playwright/python:v1.57.0-noble
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY . /app
RUN mkdir -p /app/data
EXPOSE 8000 8101
