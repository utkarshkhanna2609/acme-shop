FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && opentelemetry-bootstrap -a install
COPY app.py ./
EXPOSE 8080
ENV FLASK_APP=app.py
CMD ["opentelemetry-instrument", "flask", "run", "--host", "0.0.0.0", "--port", "8080", "--no-reload"]
