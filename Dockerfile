# Dockerfile - Ultra Fast Torrent Bot
FROM python:3.11-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

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
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /srv/seeds /srv/torrents /srv

# Copy bot code
COPY bot.py .

# Expose torrent ports
EXPOSE 6881/tcp 6881/udp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import pyrogram; print('OK')" || exit 1

# Run the bot
CMD ["python", "-u", "bot.py"]
