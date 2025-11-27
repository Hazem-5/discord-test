FROM python:3.9-slim

# Install system dependencies required for voice (ffmpeg) and building PyNaCl
RUN apt-get update && \
    apt-get install -y ffmpeg libffi-dev libnacl-dev python3-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
