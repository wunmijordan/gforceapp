#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""

import os
import sys
import socket
from django.core.management import execute_from_command_line

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't have to be reachable, just to get local IP
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gforceapp.settings')
    
    # Print the mobile-friendly clickable link before running the server
    local_ip = get_local_ip()
    print(f"\n🚀 Server running! Open this on your mobile:\nhttp://{local_ip}:8000\n")

    # Create logs folder if needed
    os.makedirs(os.path.join(os.path.dirname(__file__), 'logs'), exist_ok=True)

    try:
        execute_from_command_line(sys.argv)
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

if __name__ == '__main__':
    main()
