FROM python:3.11-slim

# Install system dependencies for packet capture
RUN apt-get update && apt-get install -y \
    libpcap-dev \
    tcpdump \
    net-tools \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python scripts
# Use COPY with explicit files to avoid cache issues
COPY traffic_monitor.py service_mapper.py api_client.py ./

# Make script executable
RUN chmod +x traffic_monitor.py

# Run as root to allow raw socket access
# In production, you'd use capabilities (CAP_NET_RAW, CAP_NET_ADMIN)
USER root

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OUTPUT_FILE=/tmp/endpoints.json

# Run the monitor
CMD ["python3", "traffic_monitor.py"]
