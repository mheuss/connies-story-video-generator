# --- Stage 1: Build React frontend ---
FROM node:22-alpine AS node-build

WORKDIR /app/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


# --- Stage 2: Python runtime ---
FROM python:3.12-slim

# System deps: FFmpeg for video assembly, fontconfig + fonts for subtitles.
# fonts-montserrat is available in Debian trixie and later.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fontconfig \
        fonts-montserrat && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[web]"

# Copy frontend build from stage 1
COPY --from=node-build /app/web/dist/ web/dist/

# Non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash appuser

# Volume mount point for project output
RUN mkdir /data && chown appuser:appuser /data

ENV PORT=8033
EXPOSE 8033

USER appuser
CMD ["story-video", "serve", "--host", "0.0.0.0", "--output-dir", "/data"]
