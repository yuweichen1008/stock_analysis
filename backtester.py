import os
import pandas as pd
import glob
from datetime import timedelta

# It's better to move the filter logic to a shared module,
# but for now, we'll import it from the existing script.
from tws.taiwan_trending import apply_filters

class Backtester:
    def __init__(self, start_date, end_date):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.ohlcv_dir = os.path.join(os.path.dirname(__file__), "data", "ohlcv")

    def _load_data(self, ticker):
        """Loads historical data for a given ticker."""
        pattern = os.path.join(self.ohlcv_dir, f"{ticker}_*.csv")
        files = glob.glob(pattern)
        if not files:
            return None
        
        df = pd.read_csv(files[0], index_col=0, parse_dates=True)
        df = df.loc[self.start_date:self.end_date]
        
        # Data cleaning
        cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=cols_to_fix)
        
        return df

    def run(self, tickers):
        """Runs the backtest for a list of tickers."""
        all_trades = []
        for ticker in tickers:
            print(f"--- Backtesting {ticker} ---")
            df = self._load_data(ticker)
            if df is None or len(df) < 120:
                print(f"Not enough data for {ticker}")
                continue

            trades = self._run_ticker_backtest(df, ticker)
            all_trades.extend(trades)

        if all_trades:
            self._calculate_performance(all_trades)
            return all_trades
        else:
            print("No trades were made during the backtest period.")
            return []

    def _run_ticker_backtest(self, df, ticker):
        trades = []
        # Iterate through each day in the dataframe
        for i in range(1, len(df) - 1):
            # The data for the filter needs to go up to the current day
            historical_df = df.iloc[:i]

            # We need enough data to calculate the indicators
            if len(historical_df) < 120:
                continue

            # Apply the filter to the historical data
            is_signal, _ = apply_filters(historical_df.copy())

            if is_signal:
                entry_date = df.index[i]
                entry_price = df['Close'].iloc[i]
                
                # Sell on the next day
                exit_date = df.index[i+1]
                exit_price = df['Close'].iloc[i+1]

                # Calculate profit
                profit = exit_price - entry_price
                profit_percent = (profit / entry_price) * 100

                trades.append({
                    "ticker": ticker,
                    "entry_date": entry_date.strftime('%Y-%m-%d'),
                    "entry_price": entry_price,
                    "exit_date": exit_date.strftime('%Y-%m-%d'),
                    "exit_price": exit_price,
                    "profit": profit,
                    "profit_percent": profit_percent,
                })
        return trades

    def _calculate_performance(self, trades):
        """Calculates and prints the performance of the backtest."""
        df_trades = pd.DataFrame(trades)
        total_trades = len(df_trades)
        winning_trades = df_trades[df_trades['profit'] > 0]
        losing_trades = df_trades[df_trades['profit'] <= 0]

        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        total_profit = df_trades['profit'].sum()
        total_profit_percent = df_trades['profit_percent'].sum()


        print("\n--- Backtest Results ---")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {len(winning_trades)}")
        print(f"Losing Trades: {len(losing_trades)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total Profit: {total_profit:.2f}")
        print(f"Total Profit (%): {total_profit_percent:.2f}%")
        print("------------------------\n")
        
        # You can also return the dataframe for further analysis
        # print(df_trades)


if __name__ == '__main__':
    # Example usage:
    # This will backtest the strategy for a few tickers from 2023-01-01 to 2023-12-31
    
    # First, let's get a list of tickers to test from the data directory
    TICKERS_DIR = os.path.join(os.path.dirname(__file__), "data", "ohlcv")
    all_files = glob.glob(os.path.join(TICKERS_DIR, "*.csv"))
    
    # Extract tickers from file names
    tickers_to_test = list(set([os.path.basename(f).split('_')[0] for f in all_files]))

    # Limit to a few tickers for a quick test
    tickers_to_test = tickers_to_test[:5]

    backtester = Backtester(start_date="2023-01-01", end_date="2023-12-31")
    backtester.run(tickers_to_test)
