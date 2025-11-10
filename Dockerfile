# syntax=docker/dockerfile:1
FROM python:3.12

# Install system dependencies
RUN apt-get update && \
    apt-get install -y git libdbus-1-dev libglib2.0-dev && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app


# Copy local code into the image
COPY . /app

# Install Python dependencies
RUN pip install .

# Environment variables (can be overridden at runtime)
ENV CITRASCOPE_PERSONAL_ACCESS_TOKEN=""
ENV CITRASCOPE_TELESCOPE_ID=""
ENV CITRASCOPE_INDI_SERVER_URL="indi"
ENV CITRASCOPE_INDI_TELESCOPE_NAME="Telescope Simulator"
ENV CITRASCOPE_INDI_CAMERA_NAME="CCD Simulator"


# Default command; can be overridden at runtime for flexibility
CMD ["python3", "-m", "citrascope", "start"]
