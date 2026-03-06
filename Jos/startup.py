#!/usr/bin/env python3
"""
Jos Sales Automation - Startup Script
Initializes platform-specific configuration and starts the sales pipeline
"""

import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Fix Windows encoding issues
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Load environment variables
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    print(f"[WARNING] .env file not found at {ENV_FILE}")
    print(f"[WARNING] Copy .env.example to .env and fill in your API keys")

# Import platform-aware config loader
try:
    from config_loader import (
        PLATFORM, IS_WINDOWS, IS_MAC, IS_LINUX,
        CONFIG_MODULE, SYSTEM
    )
except ImportError as e:
    print(f"[ERROR] Failed to import config_loader: {e}")
    sys.exit(1)

# Configure logging based on platform
if IS_WINDOWS:
    LOG_FILE = Path(r"C:\Users\autre\.openclaw\jos_logs\startup.log")
else:
    LOG_FILE = Path.home() / ".openclaw" / "jos_logs" / "startup.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def print_startup_banner():
    """Print startup banner with platform info"""
    banner = f"""
╔════════════════════════════════════════════════════════════╗
║          Jos Sales Automation - Startup                    ║
║          Queen B Revenue Generation Pipeline               ║
╚════════════════════════════════════════════════════════════╝

Platform:        {PLATFORM.upper()}
System:          {SYSTEM}
Config Module:   {CONFIG_MODULE}
Log File:        {LOG_FILE}

Initializing...
"""
    print(banner)
    logger.info(banner)

def verify_dependencies():
    """Verify all required dependencies are installed"""
    logger.info("Verifying dependencies...")
    
    dependencies = {
        "langgraph": "LangGraph",
        "langchain": "LangChain",
        "flask": "Flask",
        "apscheduler": "APScheduler",
        "tweepy": "Tweepy",
        "requests": "Requests",
        "dotenv": "python-dotenv"
    }
    
    missing = []
    for module, name in dependencies.items():
        try:
            __import__(module)
            logger.info(f"✓ {name} installed")
        except ImportError:
            logger.warning(f"✗ {name} NOT installed")
            missing.append(name)
    
    if missing:
        logger.error(f"Missing dependencies: {', '.join(missing)}")
        logger.error("Run: pip install -r requirements.txt")
        return False
    
    logger.info("✓ All dependencies verified")
    return True

def verify_api_keys():
    """Verify required API keys are configured (warnings only — fill .env to resolve)"""
    logger.info("Verifying API keys...")

    required_keys = {
        "CLAUDE_API_KEY": "Claude API",
        "X_API_KEY": "X/Twitter API",
        "X_API_SECRET": "X/Twitter Secret",
        "X_ACCESS_TOKEN": "X/Twitter Token",
        "X_ACCESS_TOKEN_SECRET": "X/Twitter Token Secret",
        "GMAIL_API_KEY": "Gmail API",
        "GMAIL_SENDER": "Gmail Sender"
    }

    missing = []
    for env_var, name in required_keys.items():
        if os.getenv(env_var):
            logger.info(f"✓ {name} configured")
        else:
            logger.warning(f"[MISSING] {name} — set {env_var} in .env")
            missing.append(env_var)

    if missing:
        logger.warning(f"Fill in .env before running the pipeline: {', '.join(missing)}")
        logger.warning(f"Template: {Path(__file__).parent / '.env.example'}")
        return False

    logger.info("✓ All API keys verified")
    return True

def verify_openclaw():
    """Verify OpenClaw is installed and running"""
    logger.info("Verifying OpenClaw...")

    import subprocess

    # Build a PATH that includes common npm global bin locations on Windows
    env = os.environ.copy()
    if IS_WINDOWS:
        extra_paths = [
            str(Path.home() / "npm-global"),
            str(Path(os.environ.get("APPDATA", "")) / "npm") if os.environ.get("APPDATA") else "",
            str(Path.home() / "AppData" / "Roaming" / "npm"),
        ]
        env["PATH"] = os.pathsep.join(filter(None, extra_paths)) + os.pathsep + env.get("PATH", "")

    # Try openclaw and openclaw.cmd (Windows)
    candidates = ["openclaw.cmd", "openclaw"] if IS_WINDOWS else ["openclaw"]
    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"✓ OpenClaw {version}")
                return True
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.warning(f"OpenClaw check error ({cmd}): {e}")
            continue

    logger.warning("✗ OpenClaw not found — restart terminal or run: npm install -g openclaw")
    return False

def verify_database():
    """Verify database is accessible"""
    logger.info("Verifying database...")
    
    try:
        from config_loader import DATABASE_PATH
        db_dir = DATABASE_PATH.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Database path: {DATABASE_PATH}")
        return True
    except Exception as e:
        logger.error(f"✗ Database verification failed: {e}")
        return False

def print_startup_checklist():
    """Print startup checklist"""
    logger.info("Running startup checklist...")
    
    # (name, check_func, blocking) — non-blocking checks warn but don't abort startup
    checks = [
        ("Dependencies", verify_dependencies, True),
        ("OpenClaw", verify_openclaw, False),
        ("Database", verify_database, True),
        ("API Keys", verify_api_keys, False),
    ]

    results = []
    for name, check_func, blocking in checks:
        try:
            result = check_func()
            results.append((name, result, blocking))
        except Exception as e:
            logger.error(f"Error during {name} check: {e}")
            results.append((name, False, blocking))

    print("\n" + "="*60)
    print("STARTUP CHECKLIST")
    print("="*60)
    for name, result, blocking in results:
        tag = "PASS" if result else ("FAIL" if blocking else "WARN")
        print(f"{name:.<40} {tag}")
    print("="*60 + "\n")

    # Only hard-fail on blocking checks
    return all(result for _, result, blocking in results if blocking)

def print_next_steps():
    """Print next steps based on platform"""
    if IS_WINDOWS:
        steps = """
NEXT STEPS (Windows - Development):
1. Start the dashboard:
   python web_dashboard.py

2. In another terminal, start the scheduler:
   python scheduler.py

3. Monitor X for leads:
   python x_scraper.py

4. Access dashboard at: http://127.0.0.1:5000

5. View OpenClaw at: http://127.0.0.1:18789
"""
    else:  # Mac
        steps = """
NEXT STEPS (Mac - Production):
1. Start the full pipeline:
   python3 joy_sales.py

2. Monitor dashboard at: http://127.0.0.1:5000

3. View OpenClaw at: http://127.0.0.1:18789

4. Check logs:
   tail -f ~/.openclaw/jos_logs/jos_mac.log

5. Queen B will run 24/7 with:
   - X monitoring every 30 minutes
   - Follow-up automation
   - Hourly email reports
   - Lead enrichment
"""
    
    print(steps)
    logger.info(steps)

def main():
    """Main startup function"""
    print_startup_banner()
    
    if not print_startup_checklist():
        logger.error("Blocking checks failed. Fix Dependencies or Database issues before continuing.")
        sys.exit(1)
    
    print_next_steps()
    
    logger.info("✓ Startup verification complete")
    logger.info(f"✓ Ready to start Jos Sales Automation on {PLATFORM.upper()}")
    print("\n✓ Startup verification complete - ready to begin!\n")

if __name__ == "__main__":
    main()
