FROM python:3.11-slim
\

\
ENV PYTHONDONTWRITEBYTECODE=1 \
\
    PYTHONUNBUFFERED=1
\

\
WORKDIR /app
\

\
# Dependencies first for cached layer
\
COPY requirements.txt .
\
RUN pip install --no-cache-dir -r requirements.txt \
\
    && adduser --disabled-password --gecos '' appuser \
\
    && chown -R appuser /app
\

\
# App code (expects main.py + other files in context)
\
COPY . .
\

\
USER appuser
\

\
# Honor Cloud Run $PORT; default 8080 locally. Also trust proxy headers.
\
CMD ["sh","-c","exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
