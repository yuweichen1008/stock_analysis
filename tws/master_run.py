import subprocess
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

# ==================== 配置環境 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
load_dotenv() # 從 .env 讀取設定

PYTHON_EXE = sys.executable 
LOG_FILE = os.path.join(BASE_DIR, "daily_run.log")

# 定義流程與顯示名稱
SCRIPTS = [
    ("get_company_info.py", "🏢 公司資料更新"),
    ("init_history_data.py", "📥 歷史數據同步"),
    ("current_trending.py", "🔍 趨勢選股分析"),
    ("telegram_notifier.py", "📢 報告發送模組")
]

def should_skip_fetch():
    """檢查今日數據是否已存在，若存在則回傳 True"""
    # 優先從 .env 讀取路徑，若無則使用預設路徑
    tickers_dir = os.getenv("TICKERS_DIR", os.path.join(BASE_DIR, "data", "tickers"))
    today_str = datetime.now().strftime("%Y%m%d")
    today_file = os.path.join(tickers_dir, f"top20_{today_str}.csv")
    
    exists = os.path.exists(today_file)
    if exists:
        print(f"[*] 偵測到今日檔案 {today_file}，將跳過下載步驟。")
    return exists

def send_status_report(summary_list, start_time):
    """發送最終執行報告至 Telegram"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[!] 錯誤：未設定 Telegram Token 或 Chat ID")
        return

    duration = datetime.now() - start_time
    report = f"📋 **TWS 每日自動化執行報告**\n"
    report += f"⏱️ 耗時: {str(duration).split('.')[0]}\n"
    report += "──────────────────\n"
    
    for name, status in summary_list:
        report += f"{status} {name}\n"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": report, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"[!] 無法發送報告: {e}")

def run_script(script_name):
    """執行腳本並捕捉詳細偵錯訊息"""
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        return False, f"❌ (找不到檔案: {script_name})"

    try:
        # 捕捉 stderr 以利偵錯
        result = subprocess.run([PYTHON_EXE, script_path], check=True, capture_output=True, text=True)
        return True, "✅"
    except subprocess.CalledProcessError as e:
        # 提取錯誤訊息的最後一行作為 Debug 資訊
        debug_msg = e.stderr.strip().split('\n')[-1] if e.stderr else f"ExitCode: {e.returncode}"
        print(f"[X] {script_name} 失敗: {debug_msg}")
        return False, f"❌ ({debug_msg})"
    except Exception as e:
        return False, f"⚠️ ({str(e)})"

def main():
    start_time = datetime.now()
    execution_summary = []
    
    # 判斷是否跳過前兩個數據抓取腳本
    is_already_fetched = should_skip_fetch()
    print(f"[*] Pipeline 開始執行。跳過抓取: {is_already_fetched}")

    for file_name, display_name in SCRIPTS:
        # 報表模組由最後統一處理，不在迴圈執行
        if file_name == "telegram_notifier.py":
            continue
            
        # 跳過邏輯：僅跳過前兩個資料更新腳本
        if is_already_fetched and file_name in ["get_company_info.py", "init_historical_data.py"]:
            execution_summary.append((display_name, "⏭️ (已跳過)"))
            continue

        success, status_icon = run_script(file_name)
        execution_summary.append((display_name, status_icon))

    # 執行選股結果通知 (telegram_notifier.py)
    # 不論前面是否跳過，最後一定要產出今日股票清單
    notif_success, notif_icon = run_script("telegram_notifier.py")
    execution_summary.append(("📢 報告發送模組", notif_icon))

    # 發送執行進度報告
    send_status_report(execution_summary, start_time)

if __name__ == "__main__":
    main()