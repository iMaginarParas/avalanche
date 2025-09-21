#!/usr/bin/env python3
"""
Entrypoint script for Railway deployment that properly handles PORT environment variable
"""
import os
import sys
import subprocess

def main():
    # Get port from environment variable, default to 8000
    port = os.environ.get('PORT', '8000')
    host = os.environ.get('HOST', '0.0.0.0')
    
    # Construct the uvicorn command
    cmd = [
        sys.executable, '-m', 'uvicorn',
        'main:app',
        '--host', host,
        '--port', port,
        '--log-level', 'info'
    ]
    
    print(f"Starting server on {host}:{port}")
    print(f"Command: {' '.join(cmd)}")
    
    # Execute uvicorn
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()