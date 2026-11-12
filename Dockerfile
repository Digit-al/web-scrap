FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\",\"8000\")}/health', timeout=4)" || exit 1

CMD ["python", "server.py"]
