#!/usr/bin/env python3
"""
Entrypoint script for Railway deployment that properly handles PORT environment variable
"""
import os
import sys

def main():
    # Get port from environment variable, default to 8000
    port = os.environ.get('PORT', '8000')
    host = os.environ.get('HOST', '0.0.0.0')
    
    print(f"Starting server on {host}:{port}")
    print(f"Environment PORT: {os.environ.get('PORT', 'NOT SET')}")
    
    # Import and run uvicorn directly instead of subprocess
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host=host,
            port=int(port),
            log_level="info"
        )
    except Exception as e:
        print(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()