# =========================
# Stage 0: Base Python Image
# =========================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Working directory
WORKDIR /app

# =========================
# Stage 1: Install System Dependencies
# =========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libgobject-2.0-0 \
    libssl-dev \
    git \
    wget \
    curl \
    shared-mime-info \
    fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# =========================
# Stage 2: Copy and Install Python Dependencies
# =========================
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# =========================
# Stage 3: Copy Project Files
# =========================
COPY . /app/

# =========================
# Stage 4: Expose Port & Start Gunicorn
# =========================
CMD ["gunicorn", "gforceapp.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--workers", "8", "--threads", "8", "--bind", "0.0.0.0:$PORT", "--timeout", "180"]