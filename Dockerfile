FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p static/maps templates

# Make main.py executable
RUN chmod +x main.py

# Initialize database
RUN python main.py --init-db

# Expose ports
EXPOSE 5000

# Default command
CMD ["python", "main.py", "--start-bot"]
