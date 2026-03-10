FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./production_agent ./production_agent

EXPOSE 8080
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8080"]
