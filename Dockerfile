# syntax=docker/dockerfile:1
FROM python:3.12

# Set working directory
WORKDIR /app

# Copy local code into the image
COPY . /app

# Run bootstrap script to install dependencies
RUN chmod +x scripts/bootstrap.sh && \
    ./scripts/bootstrap.sh && \
    rm -rf /var/lib/apt/lists/*

# Environment variables (can be overridden at runtime)
ENV CITRASCOPE_PERSONAL_ACCESS_TOKEN=""
ENV CITRASCOPE_TELESCOPE_ID=""
ENV CITRASCOPE_INDI_SERVER_URL="indi"
ENV CITRASCOPE_INDI_TELESCOPE_NAME="Telescope Simulator"
ENV CITRASCOPE_INDI_CAMERA_NAME="CCD Simulator"


# Default command; can be overridden at runtime for flexibility
CMD ["python3", "-m", "citrascope", "start"]
