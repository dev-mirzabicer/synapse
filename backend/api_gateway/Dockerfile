# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Use a virtual environment for clean dependency management
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies - path is relative to the 'backend' context
COPY api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runner - Create the final, lean image
FROM python:3.11-slim

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application code. Paths are relative to the 'backend' context.
# The trailing slash copies the *contents* of the directory.
COPY ./api_gateway/ /app
COPY ./shared/ /app/shared

# Set the path to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application using Uvicorn
# This correctly finds /app/app/main.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]