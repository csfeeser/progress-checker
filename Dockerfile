FROM python:3.12-slim

WORKDIR /app

COPY server.py .
COPY static/ static/

EXPOSE 2225

USER nobody

CMD ["python3", "server.py"]
