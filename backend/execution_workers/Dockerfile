# --------------------------------------------------------------------
# Stage 1: The Builder
#
# This stage installs all Python dependencies into a virtual environment.
# It includes build tools and results in a larger image, which we will
# discard later.
# --------------------------------------------------------------------
FROM python:3.11-slim-bookworm as builder

# Set the working directory in the container
WORKDIR /app

# Create and activate a virtual environment for clean dependency management
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy the requirements file first to leverage Docker cache
# This assumes the build context is the project root.
COPY execution_workers/requirements.txt .

# Install the Python dependencies
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------
# Stage 2: The Runner
#
# This is the final, lean image. It copies the installed dependencies
# from the builder stage and the application code. It does not contain
# any build tools.
# --------------------------------------------------------------------
FROM python:3.11-slim-bookworm

# Set the working directory
WORKDIR /app

# Create a non-root user and group to run the application
# This is a critical security best practice.
RUN addgroup --system app && adduser --system --group app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application source code into the container
# This assumes the build context is the project root.
COPY ./execution_workers/app /app
COPY ./shared /app/shared

# Set the PATH environment variable to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# Switch to the non-root user
USER app

# --------------------------------------------------------------------
# Command to run the application
#
# This command starts the ARQ worker. It tells ARQ to look for a
# class named 'WorkerSettings' inside the 'app.worker' module.
# --------------------------------------------------------------------
CMD ["arq", "app.worker.WorkerSettings"]