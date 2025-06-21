# --------------------------------------------------------------------
# Stage 1: The Builder
# --------------------------------------------------------------------
FROM python:3.11-slim-bookworm as builder

WORKDIR /app

# Create and activate a virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy requirements file, path relative to 'backend' context
COPY execution_workers/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------
# Stage 2: The Runner
# --------------------------------------------------------------------
FROM python:3.11-slim-bookworm

WORKDIR /app

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source code. Paths are relative to the 'backend' context.
# The trailing slash copies the *contents* of the directory.
COPY ./execution_workers/app/ /app
COPY ./shared/ /app/shared

# Set the PATH
ENV PATH="/opt/venv/bin:$PATH"

# Switch to the non-root user
USER app

# --------------------------------------------------------------------
# Command to run the application
# This correctly finds /app/worker.py
# --------------------------------------------------------------------
CMD ["arq", "worker.WorkerSettings"]