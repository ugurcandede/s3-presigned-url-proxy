FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Copy documentation
COPY README.md .
COPY ARCHITECTURE.md .

# Expose port 8088
EXPOSE 8088

# Configuration is provided at runtime via environment variables (see .env / docker-compose.yml).
# The application falls back to sensible defaults when a variable is unset.

# Run the application
CMD ["python", "app.py"]

