# ================================================================
# Superb Trading Strategy Backtester & Report Generator
# ---------------------------------------------------------------
# Indicators: EMA50, EMA200, RSI(14), OBV, MACD
# Entry: Trend up (EMA50 > EMA200) + RSI in [40,55] + OBV rising
# Exit: Stop-loss at swing low, Take-profit at 2x risk, or Trend flip
# ================================================================

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import matplotlib.dates as mdates

# ========================
# Data Loader
# ========================
def load_data(path="ohlcv.csv"):
    """Load OHLCV data. CSV must have: Date, Open, High, Low, Close, Volume"""
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=['Date'])
        df.set_index('Date', inplace=True)
        return df.sort_index()
    else:
        raise FileNotFoundError("Please provide ohlcv.csv with Date,Open,High,Low,Close,Volume")

# ========================
# Indicators
# ========================
def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/period, adjust=False).mean()
    ma_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def obv(df):
    obv_vals = [0]
    for i in range(1, len(df)):
        if df['Close'].iat[i] > df['Close'].iat[i-1]:
            obv_vals.append(obv_vals[-1] + df['Volume'].iat[i])
        elif df['Close'].iat[i] < df['Close'].iat[i-1]:
            obv_vals.append(obv_vals[-1] - df['Volume'].iat[i])
        else:
            obv_vals.append(obv_vals[-1])
    return pd.Series(obv_vals, index=df.index)

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# ========================
# Backtest
# ========================
def backtest(df, initial_capital=100000, risk_per_trade=0.01):
    df = df.copy().dropna()
    cash = initial_capital
    position = 0
    entry_price, stop_price = None, None
    trades = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        price = row['Close']

        # Entry conditions
        trend_up = (row['EMA50'] > row['EMA200'])
        rsi_ok = (40 <= row['RSI'] <= 55)
        obv_up = (row['OBV'] > prev['OBV'])

        if position == 0 and trend_up and rsi_ok and obv_up:
            risk_amount = cash * risk_per_trade
            recent_low = df['Low'].iloc[max(0, i-10):i].min()
            stop = recent_low if recent_low < price else price * 0.99
            risk_per_share = price - stop
            if risk_per_share > 0:
                qty = int(risk_amount / risk_per_share)
                if qty > 0:
                    position = qty
                    entry_price = price
                    stop_price = stop
                    cash -= qty * price
                    trades.append({
                        'EntryTime': row.name,
                        'Side': 'LONG',
                        'EntryPrice': price,
                        'Qty': qty,
                        'StopPrice': stop,
                        'ExitTime': None,
                        'ExitPrice': None,
                        'P&L': None,
                        'ExitReason': None
                    })

        # Manage existing position
        if position > 0:
            risk_per_share = entry_price - stop_price
            tp = entry_price + 2 * risk_per_share
            exit, reason, exit_price = False, None, None

            if row['Low'] <= stop_price:
                exit, reason, exit_price = True, "STOP", stop_price
            elif row['High'] >= tp:
                exit, reason, exit_price = True, "TP", tp
            elif row['EMA50'] < row['EMA200']:
                exit, reason, exit_price = True, "TREND_FLIP", price

            if exit:
                cash += position * exit_price
                pnl = (exit_price - entry_price) * position
                trades[-1].update({
                    'ExitTime': row.name,
                    'ExitPrice': exit_price,
                    'P&L': pnl,
                    'ExitReason': reason
                })
                position, entry_price, stop_price = 0, None, None

    # Close at end
    if position > 0:
        final_price = df['Close'].iloc[-1]
        cash += position * final_price
        pnl = (final_price - entry_price) * position
        trades[-1].update({
            'ExitTime': df.index[-1],
            'ExitPrice': final_price,
            'P&L': pnl,
            'ExitReason': "EOD"
        })

    trades_df = pd.DataFrame(trades)
    final_capital = cash
    return trades_df, final_capital

# ========================
# Performance Report
# ========================
def performance_report(trades_df, initial_capital, final_capital):
    stats = {}
    stats['InitialCapital'] = initial_capital
    stats['FinalCapital'] = final_capital
    stats['TotalReturn'] = (final_capital - initial_capital) / initial_capital
    stats['TotalP&L'] = final_capital - initial_capital
    stats['NumTrades'] = len(trades_df)
    if not trades_df.empty:
        wins = trades_df[trades_df['P&L'] > 0]
        losses = trades_df[trades_df['P&L'] <= 0]
        stats['WinRate'] = len(wins) / len(trades_df)
        stats['AvgWin'] = wins['P&L'].mean() if not wins.empty else 0
        stats['AvgLoss'] = losses['P&L'].mean() if not losses.empty else 0
    return stats

# ========================
# Plot Functions
# ========================
def plot_equity_curve(trades_df, initial_capital, df):
    equity = initial_capital
    curve = []
    eq_times = []

    for t in df.index:
        curve.append(equity)
        eq_times.append(t)
        exits = trades_df[trades_df['ExitTime'] == t]
        for _, r in exits.iterrows():
            equity += r['P&L']

    plt.figure(figsize=(12,5))
    plt.plot(eq_times, curve, label="Equity Curve", color="blue")
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.legend()
    plt.grid()
    plt.show()

def plot_trades(df, trades_df):
    plt.figure(figsize=(12,6))
    plt.plot(df['Close'], label='Close', linewidth=1)
    plt.plot(df['EMA50'], label='EMA50')
    plt.plot(df['EMA200'], label='EMA200')

    for _, r in trades_df.iterrows():
        plt.scatter(r['EntryTime'], r['EntryPrice'], marker='^', color='g', s=100)
        if pd.notnull(r['ExitPrice']):
            plt.scatter(r['ExitTime'], r['ExitPrice'], marker='v', color='r', s=100)

    plt.legend()
    plt.title("Trades on Price Chart")
    plt.show()

# ========================
# MAIN SCRIPT
# ========================
if __name__ == "__main__":
    df = load_data("ohlcv.csv")

    # Indicators
    df['EMA50'] = ema(df['Close'], 50)
    df['EMA200'] = ema(df['Close'], 200)
    df['RSI'] = rsi(df['Close'], 14)
    df['OBV'] = obv(df)
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = macd(df['Close'])

    # Run backtest
    initial_capital = 100000
    trades_df, final_capital = backtest(df, initial_capital=initial_capital)
    stats = performance_report(trades_df, initial_capital, final_capital)

    # Print report
    print("\n=== Performance Report ===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    # Save trades
    trades_df.to_csv("trades.csv", index=False)
    print("\nTrades saved to trades.csv")

    # Plots
    plot_equity_curve(trades_df, initial_capital, df)
    plot_trades(df, trades_df)
