# Dockerfile
FROM python:3.11-bullseye

# Install system dependencies for libtorrent
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libboost-python-dev \
    libboost-system-dev \
    libboost-chrono-dev \
    libboost-random-dev \
    libtorrent-rasterbar-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /srv/seeds /srv/torrents /srv

# Copy bot code
COPY bot.py .

# Expose torrent port
EXPOSE 6881/tcp 6881/udp

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "-u", "bot.py"]
