#!/bin/bash
# Railway startup script for proper PORT handling

# Set default port if PORT is not set
PORT=${PORT:-8000}

# Start the application
exec python -m uvicorn main:app --host 0.0.0.0 --port $PORT