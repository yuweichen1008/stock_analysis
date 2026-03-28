import os
import pandas as pd
import numpy as np
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
        
        # Data cleaning
        cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=cols_to_fix)
        
        return df

    def run(self, tickers, holding_days=5, stop_loss_pct=0.05, take_profit_pct=0.1, commission_pct=0.001425):
        """Runs the backtest for a list of tickers."""
        all_trades = []
        for ticker in tickers:
            print(f"--- Backtesting {ticker} ---")
            df = self._load_data(ticker)
            if df is None:
                print(f"No data for {ticker}")
                continue

            trades = self._run_ticker_backtest(df, ticker, holding_days, stop_loss_pct, take_profit_pct)
            all_trades.extend(trades)

        if all_trades:
            self._calculate_performance(all_trades, commission_pct)
            return all_trades
        else:
            print("No trades were made during the backtest period.")
            return []

    def _run_ticker_backtest(self, df, ticker, holding_days=5, stop_loss_pct=0.05, take_profit_pct=0.1):
        trades = []
        
        try:
            start_idx = df.index.searchsorted(self.start_date, side='left')
            end_idx = df.index.searchsorted(self.end_date, side='right')
        except Exception:
            print(f"Backtest date range not found in data for {ticker}")
            return []

        last_exit_i = -1
        
        for i in range(start_idx, end_idx + 1):
            if i <= last_exit_i:
                continue

            # Need at least 120 days of history before this point
            if i < 120:
                continue

            historical_df = df.iloc[:i]
            is_signal, _, metrics = apply_filters(historical_df.copy())

            if is_signal:
                entry_loc = i + 1
                if entry_loc >= len(df):
                    continue

                entry_date = df.index[entry_loc]
                entry_price = df['Open'].iloc[entry_loc]
                
                stop_loss_price = entry_price * (1 - stop_loss_pct)
                take_profit_price = entry_price * (1 + take_profit_pct)

                exit_date = None
                exit_price = None
                exit_loc = -1

                for j in range(1, holding_days + 1):
                    current_loc = entry_loc + j
                    if current_loc >= len(df):
                        break
                    
                    current_date = df.index[current_loc]
                    day_low = df['Low'].iloc[current_loc]
                    day_high = df['High'].iloc[current_loc]

                    if day_low <= stop_loss_price:
                        exit_date = current_date
                        exit_price = stop_loss_price
                        exit_loc = current_loc
                        break
                    
                    if day_high >= take_profit_price:
                        exit_date = current_date
                        exit_price = take_profit_price
                        exit_loc = current_loc
                        break

                if exit_date is None:
                    exit_loc = entry_loc + holding_days
                    if exit_loc >= len(df):
                        exit_loc = len(df) - 1
                    
                    exit_date = df.index[exit_loc]
                    exit_price = df['Close'].iloc[exit_loc]

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
                last_exit_i = exit_loc
        
        return trades

    def _calculate_performance(self, trades, commission_pct=0.001425):
        """Calculates and prints the performance of the backtest."""
        if not trades:
            print("No trades to analyze.")
            return

        df_trades = pd.DataFrame(trades)
        
        # Add commission
        df_trades['profit'] -= (df_trades['entry_price'] + df_trades['exit_price']) * commission_pct
        df_trades['profit_percent'] = (df_trades['profit'] / df_trades['entry_price']) * 100

        total_trades = len(df_trades)
        winning_trades = df_trades[df_trades['profit'] > 0]
        losing_trades = df_trades[df_trades['profit'] <= 0]

        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        total_profit = df_trades['profit'].sum()
        avg_profit_percent = df_trades['profit_percent'].mean()

        print("\n--- Backtest Results ---")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {len(winning_trades)}")
        print(f"Losing Trades: {len(losing_trades)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total Profit: {total_profit:.2f}")
        print(f"Average Profit per trade: {avg_profit_percent:.2f}%")

        # Calculate Sharpe Ratio
        df_trades['exit_date'] = pd.to_datetime(df_trades['exit_date'])
        df_trades = df_trades.sort_values(by='exit_date')
        daily_returns = df_trades.set_index('exit_date')['profit_percent'] / 100
        
        if daily_returns.std() != 0 and not np.isnan(daily_returns.std()):
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * (252**0.5)
        else:
            sharpe_ratio = 0

        # Calculate Max Drawdown
        initial_capital = 100000
        capital = initial_capital
        capital_history = [initial_capital]
        # Assuming equal investment in each trade
        investment_amount = initial_capital / 10 
        for _, trade in df_trades.iterrows():
            # Profit is per share, let's assume we buy a fixed amount
            num_shares = investment_amount / trade['entry_price']
            capital += trade['profit'] * num_shares
            capital_history.append(capital)
        
        capital_series = pd.Series(capital_history)
        peak = capital_series.expanding(min_periods=1).max()
        drawdown = (capital_series - peak) / peak
        max_drawdown = drawdown.min()


        print(f"Sharpe Ratio (annualized): {sharpe_ratio:.2f}")
        print(f"Max Drawdown: {max_drawdown:.2%}")
        print("------------------------\n")
        
        print("Example Trades:")
        print(df_trades.head())


if __name__ == '__main__':
    # This will backtest the strategy for a few tickers from 2025-10-01 to 2026-03-27
    TICKERS_DIR = os.path.join(os.path.dirname(__file__), "data", "ohlcv")
    all_files = glob.glob(os.path.join(TICKERS_DIR, "*.csv"))
    
    # Extract tickers from file names
    tickers_to_test = list(set([os.path.basename(f).split('_')[0] for f in all_files if not os.path.basename(f).startswith('00')]))

    # Limit to a few tickers for a quick test
    tickers_to_test = tickers_to_test[:10]

    backtester = Backtester(start_date="2025-10-01", end_date="2026-03-27")
    backtester.run(
        tickers_to_test, 
        holding_days=10, 
        stop_loss_pct=0.03, 
        take_profit_pct=0.1,
        commission_pct=0.001425 * 2 # buy and sell
    )