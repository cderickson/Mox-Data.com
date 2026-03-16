#!/usr/bin/env python3
"""
Local development setup script for MTGO-DB Flask application
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOCAL_DEV_DIR = SCRIPT_DIR
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 12)

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"\n{description}...")
    try:
        subprocess.run(
            command,
            shell=isinstance(command, str),
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"[OK] {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] {description} failed:")
        error_output = e.stderr or e.stdout or str(e)
        print(f"Error: {error_output}")
        return False

def create_directories():
    """Create necessary directories"""
    directories = [
        os.path.join(LOCAL_DEV_DIR, "data", "uploads"),
        os.path.join(LOCAL_DEV_DIR, "data", "logs"),
    ]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            relative_path = os.path.relpath(directory, PROJECT_ROOT)
            print(f"[OK] Created directory: {relative_path}")

def ensure_local_config():
    """Create a default local config if it does not exist."""
    config_path = os.path.join(LOCAL_DEV_DIR, "local_config.cfg")
    if os.path.exists(config_path):
        return True

    default_config = """# Local development configuration for MTGO-DB

# Flask
SECRET_KEY = 'change-me-local-secret-key'

# Mail settings (replace with your testing credentials)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'your-email@gmail.com'
MAIL_PASSWORD = 'your-app-password'
MAIL_DEFAULT_SENDER = 'your-email@gmail.com'

# Database (SQLite local file)
SQLALCHEMY_DATABASE_URI = 'sqlite:///local_database.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Celery / Redis
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# Token and email salts
URL_SAFETIMEDSERIALIZER = 'change-me-local-serializer-key'
EMAIL_CONFIRMATION_SALT = 'email-confirm-salt'
RESET_PASSWORD_SALT = 'password-reset-salt'
"""
    with open(config_path, "w", encoding="utf-8") as config_file:
        config_file.write(default_config)

    relative_path = os.path.relpath(config_path, PROJECT_ROOT)
    print(f"[OK] Created default config: {relative_path}")
    return True

def check_python_version():
    """Validate Python version against pinned dependency compatibility."""
    current = sys.version_info[:2]
    if current < MIN_PYTHON or current > MAX_PYTHON:
        min_ver = ".".join(map(str, MIN_PYTHON))
        max_ver = ".".join(map(str, MAX_PYTHON))
        current_ver = f"{current[0]}.{current[1]}"
        print("[FAIL] Unsupported Python version detected")
        print(f"Current Python: {current_ver}")
        print(f"Supported range: {min_ver} - {max_ver}")
        print("Please run this setup with Python 3.10, 3.11, or 3.12.")
        return False
    return True

def ensure_pip_available():
    """Ensure pip exists in the active interpreter/virtual environment."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        print("[WARN] pip is not available in this environment. Attempting bootstrap with ensurepip.")

    if not run_command(
        [sys.executable, "-m", "ensurepip", "--upgrade"],
        "Bootstrapping pip with ensurepip",
    ):
        print("Failed to bootstrap pip automatically.")
        print("If this is a uv environment, recreate with seeded pip:")
        print("  uv venv --python 3.12 --seed .venv")
        print("Or install with uv directly:")
        print("  uv pip install -r local-dev/requirements-local.txt")
        return False

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("[OK] pip is available in the active environment")
        return True
    except subprocess.CalledProcessError:
        print("[FAIL] pip is still unavailable after ensurepip.")
        return False

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("[OK] Redis is running")
        return True
    except Exception as e:
        print("[FAIL] Redis is not running or not accessible")
        print("Please install and start Redis:")
        print("  Windows: Download from https://redis.io/download")
        print("  macOS: brew install redis && brew services start redis")
        print("  Linux: sudo apt-get install redis-server && sudo systemctl start redis")
        return False

def main():
    print("Setting up MTGO-DB for local development...")

    if not check_python_version():
        return False
    
    # Create necessary directories
    create_directories()
    ensure_local_config()

    if not ensure_pip_available():
        print("Failed to prepare pip. Please check your Python environment.")
        return False

    # Ensure packaging tools are available before dependency resolution
    if not run_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        "Upgrading pip/setuptools/wheel",
    ):
        print("Failed to update packaging tools. Please check your Python environment.")
        return False
    
    # Install dependencies
    requirements_path = os.path.join(LOCAL_DEV_DIR, "requirements-local.txt")
    if not run_command(
        [sys.executable, "-m", "pip", "install", "-r", requirements_path],
        "Installing Python dependencies",
    ):
        print("Failed to install dependencies. Please check your Python environment.")
        return False
    
    # Check Redis
    if not check_redis():
        print("\n[WARN] Redis is required for Celery background tasks.")
        print("The app will still run, but background tasks won't work.")
    
    print("\nSetup complete!")
    print("\nTo run the application locally:")
    print("1. Make sure Redis is running (for background tasks)")
    print("2. Update local-dev/local_config.cfg with your settings")
    print("3. Run: python app.py")
    print("4. Open http://localhost:8000 in your browser")
    
    print("\nFor AWS deployment preparation:")
    print("1. Update auxiliary/config.cfg for production settings")
    print("2. Set environment variables for production")
    print("3. Use requirements.txt for production dependencies")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 