import subprocess
import os
import sys
from datetime import datetime
from dotenv import load_dotenv #

# ==================== Configuration ====================
# Load environment variables first to check for health
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

# Execution sequence
SCRIPTS = [
    "get_company_info.py",
    "init_historical_data.py",
    "current_trending.py",
    "telegram_notifier.py"
]

LOG_FILE = os.path.join(BASE_DIR, "daily_run.log")

def check_health():
    """Verifies that .env exists and contains required keys."""
    required_keys = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [key for key in required_keys if not os.getenv(key)]
    
    if missing:
        print(f"[!] Health Check Failed: Missing {missing} in .env file.")
        print("[!] Please copy .env.example to .env and fill in your credentials.")
        return False
    
    print("[✓] Environment Health Check Passed.")
    return True

def run_script(script_name):
    """Executes a child script and captures output."""
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"[!] Error: {script_name} not found.")
        return False

    print(f"[*] Executing: {script_name}...")
    try:
        # check=True will raise an exception if the script fails
        subprocess.run([PYTHON_EXE, script_path], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[X] Failure in {script_name}:")
        print(f"Error Output: {e.stderr}")
        return False

def main():
    start_time = datetime.now()
    print(f"--- Pipeline Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    # 1. Start with Health Check
    if not check_health():
        sys.exit(1)

    # 2. Run sequential scripts
    success_count = 0
    for script in SCRIPTS:
        if run_script(script):
            success_count += 1
        else:
            print(f"[!] Pipeline aborted at {script}.")
            break

    # 3. Final Summary
    end_time = datetime.now()
    duration = end_time - start_time
    summary = f"--- Finished: {success_count}/{len(SCRIPTS)} successful. Duration: {duration} ---\n"
    print(summary.strip())

    # Log the summary for historical tracking
    with open(LOG_FILE, "a") as f:
        f.write(f"{start_time}: {summary}")

if __name__ == "__main__":
    main()