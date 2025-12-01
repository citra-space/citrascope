# syntax=docker/dockerfile:1
FROM python:3.12


# Install system dependencies (match devcontainer setup)
RUN apt-get update && \
    apt-get install -y git cmake libdbus-1-dev libglib2.0-dev libjpeg-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app


# Copy local code into the image
COPY . /app


# Upgrade pip and install Python dependencies
RUN python3 -m pip install --upgrade pip && pip install .[all]

# Environment variables (can be overridden at runtime)
ENV CITRASCOPE_PERSONAL_ACCESS_TOKEN=""
ENV CITRASCOPE_TELESCOPE_ID=""
ENV CITRASCOPE_INDI_SERVER_URL="indi"
ENV CITRASCOPE_INDI_TELESCOPE_NAME="Telescope Simulator"
ENV CITRASCOPE_INDI_CAMERA_NAME="CCD Simulator"


# Default command; can be overridden at runtime for flexibility
CMD ["python3", "-m", "citrascope", "start"]
