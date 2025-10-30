# Build stage: install dependencies into a virtual environment
FROM python:3.11-slim AS build
ARG NODE_VERSION=18.19.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system deps, Node.js for frontend build, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/local/etc \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock ./
COPY app ./app
COPY frontend ./frontend
COPY README.md ./

# Install dependencies into a venv (for smaller runtime image)
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

# Build frontend assets
RUN cd frontend \
    && npm install \
    && npm run build

RUN /opt/venv/bin/playwright install --with-deps chromium

# Runtime image
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install runtime requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgtk-3-0 \
    libasound2 \
    libnss3 \
    libnspr4 \
    libxcb1 \
    libxext6 \
    libcups2 \
    libxss1 \
    libxcursor1 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxshmfence1 \
    libgbm1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
COPY --from=build /root/.cache/ms-playwright ${PLAYWRIGHT_BROWSERS_PATH}
COPY --from=build /app/app ./app
COPY --from=build /app/frontend/dist ./static
COPY --from=build /app/README.md ./
COPY --from=build /app/pyproject.toml /app/uv.lock ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
