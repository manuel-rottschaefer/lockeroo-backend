# ---------- Stage 1: Build Layer ----------
FROM python:3.13-slim AS builder

# Set up working directory
WORKDIR /app

# Install system dependencies required for MongoDB tools & Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg curl ca-certificates lsb-release build-essential \
    && curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg \
    && echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/debian $(lsb_release -sc)/mongodb-org/7.0 main" > /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    mongodb-mongosh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install MongoDB Database Tools (includes mongorestore)
RUN curl -fsSL https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-100.9.4.deb -o mongodb-tools.deb \
    && apt-get update && apt-get install -y ./mongodb-tools.deb \
    && rm mongodb-tools.deb

# Copy requirements separately to leverage Docker cache
COPY Lockeroo_Backend/requirements.txt .

# Install Python dependencies into a virtual env in a cacheable layer
RUN python -m venv /venv && \
    . /venv/bin/activate && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install the shared models package
COPY Lockeroo_Models /tmp/models
RUN . /venv/bin/activate && pip install /tmp/models


# ---------- Stage 2: Final Runtime Layer ----------
FROM python:3.13-slim

# Set up working directory
WORKDIR /app

# Copy over the virtual environment from builder
COPY --from=builder /venv /venv

# Activate the virtual environment by default
ENV PATH="/venv/bin:$PATH"

# Copy MongoDB CLI tools from builder
COPY --from=builder /usr/bin/mongosh /usr/bin/mongosh
COPY --from=builder /usr/bin/mongorestore /usr/bin/mongorestore
COPY --from=builder /usr/lib /usr/lib
COPY --from=builder /usr/share /usr/share
COPY --from=builder /lib /lib

# Copy application code
COPY Lockeroo_Backend/. .

# Expose backend port
EXPOSE 4020

# Run backend
CMD ["sh", "-c", "python -u main.py"]
