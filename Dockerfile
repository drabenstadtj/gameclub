# Use a slim Python base image
FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Set environment to production
ENV PYTHONUNBUFFERED=1
ENV PORT=5000 

# Run both Flask (via Gunicorn) and the bot
CMD ["sh", "-c", "gunicorn web_app.wsgi:app --bind 0.0.0.0:$PORT & python bot/bot.py"]
