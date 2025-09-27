import requests
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# --------------------------
# Helper: Safe timestamp conversion
# --------------------------
def convert_timestamp(series):
    """Convert timestamps automatically (seconds or milliseconds)."""
    if series.max() > 1e12:  # too large, must be ms
        return pd.to_datetime(series, unit="ms")
    else:
        return pd.to_datetime(series, unit="s")

# --------------------------
# Fetch OHLCV data
# --------------------------
def get_daily_ohlcv(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=100"
    response = requests.get(url)

    if response.status_code != 200:
        return pd.DataFrame()

    data = response.json()
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    df["timestamp"] = convert_timestamp(df["timestamp"].astype(float))
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df[["timestamp", "close", "volume"]]

# --------------------------
# Whale Strength Score
# --------------------------
def calculate_whale_strength(df):
    if df.empty:
        return None
    avg_volume = df["volume"].mean()
    last_volume = df["volume"].iloc[-1]
    score = (last_volume / avg_volume) * 100
    return round(score, 2)

# --------------------------
# Streamlit App
# --------------------------
st.title("🐋 Whale Accumulation Strength Dashboard")

symbol = st.text_input("Enter Coin Symbol (Binance format, e.g., BTCUSDT)", "BTCUSDT").upper()

if st.button("Analyze"):
    df = get_daily_ohlcv(symbol)

    if df.empty:
        st.error("⚠️ Data unavailable. Try another symbol (e.g., ETHUSDT, BNBUSDT).")
    else:
        # Whale Strength
        score = calculate_whale_strength(df)
        st.metric(label=f"Whale Strength Score ({symbol})", value=f"{score}%")

        # Chart
        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax1.plot(df["timestamp"], df["close"], label="Close Price", color="blue")
        ax2 = ax1.twinx()
        ax2.bar(df["timestamp"], df["volume"], alpha=0.3, color="orange", label="Volume")
        ax1.set_title(f"{symbol} - Price & Volume")
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Price (USDT)")
        ax2.set_ylabel("Volume")
        st.pyplot(fig)