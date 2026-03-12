import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf

# Get Tesla's real data
try:
    tsla = yf.download('TSLA', start='2024-01-01', end='2024-04-10')
    if tsla.empty:
        raise Exception("No data returned from yfinance")
        
    # Convert the 2D array to 1D by flattening it
    price_series = pd.Series(tsla['Close'].values.flatten(), index=tsla.index)
    
    # Parameters
    h = 10  # maximum holding period
    pt_sl = [0.03, 0.02]  # profit-taking at +3%, stop-loss at -2%
    trgt = price_series.pct_change().ewm(span=20).std()  # volatility estimate
    
except Exception as e:
    print(f"Error fetching Tesla data: {str(e)}")
    raise

# Triple-barrier labeling function
def apply_triple_barrier(price_series, pt_sl, trgt, max_hold):
    labels = pd.Series(index=price_series.index, dtype=int)
    barriers = pd.DataFrame(index=price_series.index, columns=['upper', 'lower'])

    for t0 in price_series.index[:-max_hold]:
        start_price = price_series[t0]
        end_idx = price_series.index.get_loc(t0) + max_hold
        window = price_series.iloc[price_series.index.get_loc(t0):end_idx+1]
        trgt_val = trgt[t0]

        if pd.isna(trgt_val):
            labels[t0] = 0
            barriers.loc[t0] = [np.nan, np.nan]
            continue

        upper_barrier = start_price * (1 + pt_sl[0] * trgt_val)
        lower_barrier = start_price * (1 - pt_sl[1] * trgt_val)
        barriers.loc[t0] = [upper_barrier, lower_barrier]

        label = 0  # default label
        for time, price in window.items():
            if price >= upper_barrier:
                label = 1
                break
            elif price <= lower_barrier:
                label = -1
                break
        labels[t0] = label

    return labels, barriers

# Apply the triple-barrier method
labels, barriers = apply_triple_barrier(price_series, pt_sl, trgt, h)

# Plot price series with barriers
plt.figure(figsize=(15, 7))
plt.plot(price_series.index, price_series.values, label='TSLA Price')

# Plot barriers for each starting point
for idx in barriers.index[:-h]:
    if not pd.isna(barriers.loc[idx, 'upper']):
        plt.hlines(barriers.loc[idx, 'upper'], idx, 
                  price_series.index[price_series.index.get_loc(idx) + h], 
                  colors='g', linestyles='--', alpha=0.3)
        plt.hlines(barriers.loc[idx, 'lower'], idx,
                  price_series.index[price_series.index.get_loc(idx) + h], 
                  colors='r', linestyles='--', alpha=0.3)

plt.title('Tesla Stock Price with Triple Barriers')
plt.xlabel('Date')
plt.ylabel('Price')
plt.legend()
plt.grid(True)
plt.show()

import ace_tools as tools; tools.display_dataframe_to_user(name="Triple-Barrier Labels", dataframe=labels.to_frame("label"))
