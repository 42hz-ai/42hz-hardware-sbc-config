# Telemetry publisher for Greengrass v2 Docker container components (SBCC-INFRA-0003).
# Build for the core device arch — e.g. linux/amd64 (devcontainer) or linux/arm64 (Pi).

FROM docker.io/library/python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir "awsiotsdk>=1.21.0"

WORKDIR /app
COPY publisher.py /app/publisher.py

ENTRYPOINT ["python3", "-u", "/app/publisher.py"]
CMD ["5"]
