#!/usr/bin/env python
"""
Status Check Script for RSI Layered Extreme Value Tracking Trading System

This script checks if both the backend and frontend servers are running and accessible.
It performs basic connectivity tests and API endpoint checks.
"""

import sys
import socket
import time
import json
import argparse
from urllib.parse import urlparse
from datetime import datetime

try:
    import requests
    from requests.exceptions import RequestException
    from colorama import init, Fore, Style
    
    # Initialize colorama for colored terminal output
    init()
except ImportError:
    print("Required packages not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "colorama"])
    import requests
    from requests.exceptions import RequestException
    from colorama import init, Fore, Style
    init()

# Configuration
BACKEND_URL = "http://localhost:8080"
FRONTEND_URL = "http://localhost:3000"
BACKEND_API_ENDPOINT = "/api/v1/system/status"
TIMEOUT = 5  # seconds

def print_header():
    """Print script header with timestamp"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f" RSI Layered Extreme Value Tracking Trading System - Status Check")
    print(f" {now}")
    print(f"{'='*60}{Style.RESET_ALL}\n")

def check_port_open(host, port):
    """Check if a port is open on the given host"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.error:
        return False

def check_backend_status():
    """Check if the backend server is running and responding"""
    print(f"{Fore.BLUE}Checking backend server...{Style.RESET_ALL}")
    
    # Parse URL to get host and port
    parsed_url = urlparse(BACKEND_URL)
    host = parsed_url.hostname
    port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
    
    # Check if port is open
    if not check_port_open(host, port):
        print(f"{Fore.RED}[FAIL] Backend server is not running (port {port} is closed){Style.RESET_ALL}")
        return False
    
    # Check API endpoint
    try:
        response = requests.get(f"{BACKEND_URL}{BACKEND_API_ENDPOINT}", timeout=TIMEOUT)
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"{Fore.GREEN}[OK] Backend server is running{Style.RESET_ALL}")
                print(f"  - Version: {data.get('version', 'Unknown')}")
                print(f"  - Status: {data.get('status', 'Unknown')}")
                print(f"  - Uptime: {data.get('uptime', 'Unknown')}")
                print(f"  - Active strategies: {data.get('active_strategies', 'Unknown')}")
                print(f"  - Active positions: {data.get('active_positions', 'Unknown')}")
                return True
            except json.JSONDecodeError:
                print(f"{Fore.YELLOW}[OK] Backend server is running but returned invalid JSON{Style.RESET_ALL}")
                return True
        else:
            print(f"{Fore.YELLOW}[OK] Backend server is running but returned status code {response.status_code}{Style.RESET_ALL}")
            return True
    except RequestException as e:
        print(f"{Fore.RED}[FAIL] Backend API endpoint is not responding: {str(e)}{Style.RESET_ALL}")
        return False

def check_frontend_status():
    """Check if the frontend server is running and responding"""
    print(f"\n{Fore.BLUE}Checking frontend server...{Style.RESET_ALL}")
    
    # Parse URL to get host and port
    parsed_url = urlparse(FRONTEND_URL)
    host = parsed_url.hostname
    port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
    
    # Check if port is open
    if not check_port_open(host, port):
        print(f"{Fore.RED}[FAIL] Frontend server is not running (port {port} is closed){Style.RESET_ALL}")
        return False
    
    # Check frontend homepage
    try:
        response = requests.get(FRONTEND_URL, timeout=TIMEOUT)
        if response.status_code == 200:
            print(f"{Fore.GREEN}[OK] Frontend server is running{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}[OK] Frontend server is running but returned status code {response.status_code}{Style.RESET_ALL}")
            return True
    except RequestException as e:
        print(f"{Fore.RED}[FAIL] Frontend server is not responding: {str(e)}{Style.RESET_ALL}")
        return False

def check_system_status():
    """Check the status of the entire system"""
    print_header()
    
    backend_ok = check_backend_status()
    frontend_ok = check_frontend_status()
    
    print(f"\n{Fore.BLUE}Summary:{Style.RESET_ALL}")
    if backend_ok and frontend_ok:
        print(f"{Fore.GREEN}[OK] System is fully operational{Style.RESET_ALL}")
        return 0
    elif backend_ok:
        print(f"{Fore.YELLOW}⚠ System is partially operational (frontend is down){Style.RESET_ALL}")
        return 1
    elif frontend_ok:
        print(f"{Fore.YELLOW}⚠ System is partially operational (backend is down){Style.RESET_ALL}")
        return 1
    else:
        print(f"{Fore.RED}[FAIL] System is not operational (both services are down){Style.RESET_ALL}")
        return 2

def main():
    """Main function"""
    # Declare that we intend to modify the module-level constants.
    # This declaration must appear before any reference (read or write)
    # to the names within the current function to avoid the
    # “name used prior to global declaration” `SyntaxError`.
    global BACKEND_URL, FRONTEND_URL

    parser = argparse.ArgumentParser(description='Check the status of RSI Layered Extreme Value Tracking Trading System')
    parser.add_argument('--backend', default=BACKEND_URL, help=f'Backend URL (default: {BACKEND_URL})')
    parser.add_argument('--frontend', default=FRONTEND_URL, help=f'Frontend URL (default: {FRONTEND_URL})')
    parser.add_argument('--watch', action='store_true', help='Watch mode - continuously monitor status')
    parser.add_argument('--interval', type=int, default=30, help='Interval in seconds for watch mode (default: 30)')
    
    args = parser.parse_args()
    
    BACKEND_URL = args.backend
    FRONTEND_URL = args.frontend
    
    if args.watch:
        print(f"Monitoring system status every {args.interval} seconds. Press Ctrl+C to stop.")
        try:
            while True:
                status = check_system_status()
                print(f"\nWaiting {args.interval} seconds for next check...\n")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            return 0
    else:
        return check_system_status()

if __name__ == "__main__":
    sys.exit(main())
