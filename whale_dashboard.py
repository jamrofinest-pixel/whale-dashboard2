import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(
    page_title="🐋 Whale Accumulation Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE = "https://api.coingecko.com/api/v3"

# -------------------------------
# DATA FETCHING
# -------------------------------
def get_daily_ohlcv(symbol: str, days: int = 90):
    """Fetch OHLCV data from Coingecko"""
    url = f"{API_BASE}/coins/{symbol}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])

        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        df["volume"] = [v[1] for v in volumes]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        st.error(f"⚠️ Data fetch failed: {e}")
        return pd.DataFrame()

def whale_accumulation_strength(df: pd.DataFrame):
    """Simple whale accumulation indicator"""
    if df.empty:
        return pd.Series(dtype=float)
    # Use rolling z-score of volume spikes as proxy
    df["vol_ma"] = df["volume"].rolling(7).mean()
    df["strength"] = (df["volume"] - df["vol_ma"]) / (df["vol_ma"] + 1)
    return df["strength"]

# -------------------------------
# UI SIDEBAR
# -------------------------------
st.sidebar.header("⚙️ Settings")
symbol = st.sidebar.text_input("Enter Coin ID (from Coingecko)", "bitcoin")
days = st.sidebar.slider("Days of Data", 30, 365, 90)

st.sidebar.markdown("---")
st.sidebar.write("Examples: `bitcoin`, `ethereum`, `dogecoin`")

# -------------------------------
# MAIN APP
# -------------------------------
st.title("🐋 Whale Accumulation Strength Dashboard")
st.markdown("Track whale accumulation signals using on-chain volume analysis (via Coingecko API).")

df = get_daily_ohlcv(symbol, days)

if df.empty:
    st.warning("No data available. Try another coin ID.")
    st.stop()

df["strength"] = whale_accumulation_strength(df)

# -------------------------------
# METRICS
# -------------------------------
latest_price = df["price"].iloc[-1]
latest_strength = df["strength"].iloc[-1]
avg_strength = df["strength"].mean()

col1, col2, col3 = st.columns(3)
col1.metric("Latest Price (USD)", f"${latest_price:,.2f}")
col2.metric("Current Whale Strength", f"{latest_strength:.2f}")
col3.metric("Avg Whale Strength", f"{avg_strength:.2f}")

# -------------------------------
# CHARTS
# -------------------------------
fig, ax1 = plt.subplots(figsize=(12,6))

ax1.plot(df["timestamp"], df["price"], color="blue", label="Price (USD)")
ax1.set_ylabel("Price (USD)", color="blue")
ax1.tick_params(axis="y", labelcolor="blue")

ax2 = ax1.twinx()
ax2.bar(df["timestamp"], df["strength"], color="orange", alpha=0.3, label="Whale Strength")
ax2.set_ylabel("Strength", color="orange")
ax2.tick_params(axis="y", labelcolor="orange")

fig.tight_layout()
st.pyplot(fig)

# -------------------------------
# SMART INSIGHTS
# -------------------------------
st.subheader("📊 Smart Insights")
if latest_strength > avg_strength * 1.5:
    st.success("🐳 Strong Whale Accumulation Detected — whales are buying heavily.")
elif latest_strength < avg_strength * 0.5:
    st.error("🐟 Weak Accumulation — whale activity appears low.")
else:
    st.info("📈 Neutral Whale Activity — within normal range.")

# -------------------------------
# RAW DATA TABLE
# -------------------------------
with st.expander("See Raw Data Table"):
    st.dataframe(df.tail(20))

st.caption("Powered by Streamlit + Coingecko API | Educational use only")