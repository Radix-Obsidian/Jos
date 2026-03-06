"""
Platform-aware configuration loader for Jos Sales Automation
Automatically detects OS and loads appropriate configuration
"""

import os
import sys
import platform
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Detect platform
SYSTEM = platform.system()
IS_WINDOWS = sys.platform.startswith("win") or SYSTEM == "Windows"
IS_MAC = sys.platform == "darwin" or SYSTEM == "Darwin"
IS_LINUX = sys.platform.startswith("linux") or SYSTEM == "Linux"

# Get platform from environment or auto-detect
PLATFORM = os.getenv("PLATFORM", "").lower()
if not PLATFORM:
    if IS_WINDOWS:
        PLATFORM = "windows"
    elif IS_MAC:
        PLATFORM = "mac"
    elif IS_LINUX:
        PLATFORM = "linux"
    else:
        PLATFORM = "unknown"

print(f"[Jos Config] Detected platform: {PLATFORM} (system: {SYSTEM})")

# Import platform-specific config
if PLATFORM == "windows":
    from config_windows import *
    CONFIG_MODULE = "config_windows"
elif PLATFORM == "mac":
    from config_mac import *
    CONFIG_MODULE = "config_mac"
else:
    # Fallback to Windows config for unknown platforms
    from config_windows import *
    CONFIG_MODULE = "config_windows"

print(f"[Jos Config] Loaded configuration from {CONFIG_MODULE}")

# Validate required environment variables
REQUIRED_ENV_VARS = [
    "CLAUDE_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "GMAIL_API_KEY",
    "GMAIL_SENDER"
]

MISSING_VARS = []
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        MISSING_VARS.append(var)

if MISSING_VARS:
    print(f"[Jos Config] WARNING: Missing environment variables: {', '.join(MISSING_VARS)}")
    print(f"[Jos Config] Please set these in your .env file or environment")
else:
    print(f"[Jos Config] All required environment variables are set")

# Export platform info
__all__ = [
    "PLATFORM",
    "IS_WINDOWS",
    "IS_MAC",
    "IS_LINUX",
    "CONFIG_MODULE",
    "SYSTEM"
]
