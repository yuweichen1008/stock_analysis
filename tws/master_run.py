import subprocess
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

# ==================== Configuration ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

PYTHON_EXE = sys.executable 
SCRIPTS = [
    ("get_company_info.py", "🏢 公司資料更新"),
    ("init_history_crawler.py", "📥 歷史數據同步"),
    ("current_trending.py", "🔍 趨勢選股分析"),
    ("telegram_notifier.py", "📢 報告發送模組")
]

def send_status_report(summary_list, start_time):
    """Sends the final execution summary to Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("[!] Telegram credentials missing.")
        return

    duration = datetime.now() - start_time
    report = f"📋 **TWS 每日自動化執行報告**\n"
    report += f"⏱️ 耗時: {str(duration).split('.')[0]}\n"
    report += "──────────────────\n"
    
    for name, status in summary_list:
        report += f"{status} {name}\n"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": report, "parse_mode": "Markdown"}, timeout=10)

def run_script(script_name):
    script_path = os.path.join(BASE_DIR, script_name)
    try:
        # 捕捉 stderr 以取得具體錯誤
        result = subprocess.run([PYTHON_EXE, script_path], check=True, capture_output=True, text=True)
        return True, "✅"
    except subprocess.CalledProcessError as e:
        # 取得錯誤訊息的最後一行 (通常是具體的 Error Name)
        error_msg = e.stderr.strip().split('\n')[-1]
        return False, f"❌ ({error_msg})"
    except Exception as e:
        return False, "⚠️ (系統錯誤)"

def main():
    start_time = datetime.now()
    execution_summary = []
    
    print(f"[*] Starting Pipeline at {start_time}")

    for file_name, display_name in SCRIPTS:
        # Skip the notifier here, as we run it as a custom status report at the end
        if file_name == "telegram_notifier.py":
            continue
            
        success, icon = run_script(file_name)
        execution_summary.append((display_name, icon))
        
        # If a critical data step fails, we log it but don't break, 
        # so the final report can still be sent.
        if not success:
            print(f"[!] {file_name} failed.")

    # Final step: Always send the report
    # We include the notifier result itself as part of the summary
    print("[*] Sending status report...")
    send_status_report(execution_summary, start_time)

if __name__ == "__main__":
    main()