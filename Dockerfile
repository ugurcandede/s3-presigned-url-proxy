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

# Set environment variables (will be overridden by docker-compose)
ENV AWS_REGION=us-east-1
ENV PRESIGNED_URL_EXPIRATION=14400

# Run the application
CMD ["python", "app.py"]

