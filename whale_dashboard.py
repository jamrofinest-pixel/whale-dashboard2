import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime

# --------------------------
# Helper function to fetch OHLCV
# --------------------------
def get_daily_ohlcv(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval=1d&limit=100"
    response = requests.get(url)
    if response.status_code != 200:
        return None
    
    data = response.json()
    if not data:
        return None
    
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "trades",
        "taker_base_vol", "taker_quote_vol", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df[["timestamp", "close", "volume"]]

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="Whale Dashboard", layout="wide")
st.title("🐋 Whale Accumulation Strength Dashboard")

symbol = st.text_input("Enter a coin symbol (e.g., BTC, ETH):", "BTC")

if st.button("Scan"):
    df = get_daily_ohlcv(symbol)
    if df is None or df.empty:
        st.error("❌ Data unavailable. Try another symbol (e.g., BTC, ETH).")
    else:
        st.success(f"✅ Showing data for {symbol.upper()}USDT")

        # Price chart
        fig, ax1 = plt.subplots(figsize=(10, 4))
        ax1.plot(df["timestamp"], df["close"], label="Close Price", color="blue")
        ax1.set_ylabel("Price (USDT)")
        ax1.set_title(f"{symbol.upper()} Price Chart")
        ax1.legend()
        st.pyplot(fig)

        # Volume chart
        fig, ax2 = plt.subplots(figsize=(10, 3))
        ax2.bar(df["timestamp"], df["volume"], color="orange", alpha=0.6)
        ax2.set_ylabel("Volume")
        ax2.set_title(f"{symbol.upper()} Trading Volume")
        st.pyplot(fig)

        # Whale strength metric (simplified)
        avg_volume = df["volume"].mean()
        last_volume = df["volume"].iloc[-1]
        strength = (last_volume / avg_volume) * 100
        st.metric("Whale Accumulation Strength (%)", f"{strength:.2f}%")