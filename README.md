🚀 TWS AI Stock Analyst   
TWS (Taiwan Stock) AI Analyst 是一款專為台股設計的自動化量化分析工具。它整合了證交所官方數據、Yahoo Finance 金融指標，並利用 Ledoit-Wolf 縮減估計模型 進行短線價格預測，最後透過 Telegram Bot 提供即時互動查詢。

🌟 核心功能 (Key Features)  
自動化數據流水線 (Automated Pipeline)：每日自動同步證交所熱門標的，並抓取 250 日 K 線數據。

多維度金融引擎 (Fundamental Engine)：自動追蹤 ROE、PE、負債比與殖利率，並具備 90 天自動更新機制。

時點資料日誌 (Point-in-Time Logging)：建立 company_history.csv，完整記錄財報變動，為未來「策略回測」奠定基礎。

量化趨勢過濾：內建 MA5、MA20、MA120 趨勢濾網，自動識別多頭強勢股並排除空頭陷阱。

AI 價格預測：採用 Ledoit-Wolf Shrinkage Estimator 算法，降低金融數據雜訊，提供穩健的 5 日目標價預測。

Telegram 互動助理：支援即時輸入代碼查詢，秒級回傳財務體質報告與 AI 預測燈號（🔴/🟢）。

📂 專案結構 (Project Structure)
```
stock_analysis/
├── master_run.py          # 每日自動化流程入口 (排程執行)
├── app.py                 # Telegram Bot 互動入口 (長駐執行)
├── .env                   # 環境變數配置 (Token, ID)
├── data/                  # 數據存儲中心
│   ├── ohlcv/             # 歷史 K 線 CSV
│   ├── tickers/           # 每日熱門標清單
│   └── company/           # 基本面快照與歷史日誌
└── tws/                   # 核心邏輯套件
    ├── core.py            # 數據同步與補全引擎
    ├── taiwan_trending.py # 台股選股演算法
    ├── telegram_notifier.py # 自動化報告模組
    ├── models.py          # Ledoit-Wolf AI 預測模型
    └── utils.py           # Telegram 與新聞工具類
```

🛠️ 快速開始 (Getting Started)
1. 環境安裝
Bash
pip install pandas yfinance requests python-telegram-bot scikit-learn PyPortfolioOpt
2. 環境變數配置
建立 .env 檔案並填入資訊：
```
TELEGRAM_BOT_TOKEN=你的機器人Token
TELEGRAM_CHAT_ID=你的頻道ID
```
3. 運行模式
每日掃描：執行 `python master_run.py` 以獲取當日強勢股報告。

開啟助理：執行 `python app.py` 啟動 Telegram 即時對話功能。

📈 算法說明 (Algorithm Insights)
本項目目前的預測核心為 Ledoit-Wolf 縮減估計。
在金融數據分析中，直接計算斜方差矩陣往往會因為樣本雜訊過大而失真。Ledoit-Wolf 透過將樣本矩陣向目標矩陣「縮減」的方式，提供了更穩定的二階矩估計，這對於短線趨勢的風險控管與價格定位至關重要。

🗺️ 路線圖 (Roadmap)  

- [x] Milestone 1: 核心數據引擎、自動補全機制、Telegram 基礎互動、歷史日誌系統。  
- [ ] Milestone 2: 整合 Plotly 視覺化 K 線圖傳送、加入乖離率 (Bias) 因子。  
- [ ] Milestone 3: 實作回測系統 (Backtester)、對接美股分析模組。  
- [ ] Milestone 4: 引入 LSTM 或 Transformer 深度學習模型優化預測。

🤝 貢獻與開發  
這個項目目前由 Gemini AI 開發