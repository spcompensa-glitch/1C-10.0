# Use official Python runtime as a parent image
# Build trigger: 2026-06-03 (V110.708 Resilient Auth endpoints)
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# V5.2.4.4: Force native DNS resolver for Google API stability in Cloud Run
ENV GRPC_DNS_RESOLVER=native

# Set work directory
WORKDIR /app

# Install system dependencies for crypto and robust SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    ca-certificates \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Update CA Certificates to ensure SSL handshake stability
RUN update-ca-certificates

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies (Chromium)
RUN playwright install --with-deps chromium

# Copy the entire project
COPY . .

# Set frontend directory as static root
WORKDIR /app

# Expose port (Railway Standard: 8085)
ENV PORT=8085
EXPOSE 8085

# Command to run the application using Uvicorn (Railway Standard with Fixed Port 8085 to match proxy routing)
CMD uvicorn backend.main:app --host 0.0.0.0 --port 8085 --workers 1

