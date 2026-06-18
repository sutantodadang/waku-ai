FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY config.py llm.py nlu.py conversation.py ai_service.py ./

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import http.client; conn=http.client.HTTPConnection('localhost:8001'); conn.request('GET','/health'); resp=conn.getresponse(); exit(0) if resp.status==200 else exit(1)"

# Run
CMD ["uvicorn", "ai_service:app", "--host", "0.0.0.0", "--port", "8001"]
