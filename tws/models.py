import numpy as np
import pandas as pd
from pypfopt import risk_models, expected_returns

class StockAI:
    @staticmethod
    def predict_target(prices_df):
        """
        使用 Ledoit-Wolf 風險穩定化模型預估 5 日目標價
        解決 FutureWarning: Calling float on a single element Series
        """
        try:
            # 確保資料足夠進行協方差運算 (建議至少 20 天)
            if prices_df is None or len(prices_df) < 20:
                return "N/A", "N/A"

            # 🛡️ 核心修復：使用 .iloc[-1, 0] 確保獲取純數值純量，避免 Series 轉換警告
            current_price = float(prices_df.iloc[-1, 0])
            
            # 1. 計算資產收益率
            mu = expected_returns.mean_historical_return(prices_df)
            
            # 2. Ledoit-Wolf 風險收縮 (縮小估計誤差，讓預測更穩健)
            # 這能處理樣本數不足或波動異常的問題
            shrunk_cov = risk_models.CovarianceShrinkage(prices_df).ledoit_wolf()
            volatility = np.sqrt(np.diag(shrunk_cov))[-1]
            
            # 3. 簡單預測邏輯：基於平均收益率與波動率調整
            # 這裡設定 5 日預測溢價，並根據波動率進行風險扣除
            expected_gain = (mu.iloc[0] / 252 * 5) - (volatility * 0.05)
            predicted_price = current_price * (1 + expected_gain)
            
            return round(current_price, 2), round(predicted_price, 2)
        except Exception as e:
            print(f"   [!] AI 預測失敗: {e}")
            return "N/A", "N/A"