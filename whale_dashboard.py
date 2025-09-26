import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime

st.set_page_config(page_title="Whale Accumulation Strength Dashboard", layout="wide")

# --------------------------
# Helper: Safe timestamp conversion
# --------------------------
def convert_timestamp(series):
    series = pd.to_numeric(series, errors='coerce')
    if series.max() > 1e12:
        return pd.to_datetime(series, unit="ms")
    else:
        return pd.to_datetime(series, unit="s")

# --------------------------
# Fetch daily OHLCV data from Bybit (robust)
# --------------------------
def get_daily_ohlcv(symbol='BTCUSDT', limit=30):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1440&limit={limit}"
        res = requests.get(url, timeout=10).json()
        if 'result' not in res or 'list' not in res['result'] or not res['result']['list']:
            return None
        data = res['result']['list']
        df = pd.DataFrame(data, columns=['timestamp','open','high','low','close','volume','turnover'])
        df['timestamp'] = convert_timestamp(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        return df[['open','high','low','close','volume']].astype(float)
    except Exception as e:
        st.error(f"{symbol}: Failed to fetch OHLCV ({e})")
        return None

# --------------------------
# OBV calculation
# --------------------------
def calculate_obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i - 1]:
            obv.append(obv[-1] + df['volume'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i - 1]:
            obv.append(obv[-1] - df['volume'].iloc[i])
        else:
            obv.append(obv[-1])
    df['obv'] = obv
    return df

# --------------------------
# Accumulation / Distribution detection
# --------------------------
def detect_accumulation(df, lookback=5):
    recent = df.tail(lookback)
    price_change = recent['close'].pct_change().sum()
    volume_change = recent['volume'].pct_change().sum()
    volatility = recent['high'].max() - recent['low'].min()
    avg_price = recent['close'].mean()
    if volume_change > 0.2 and abs(price_change) < 0.01 and volatility < 0.05 * avg_price:
        return "Accumulation"
    elif volume_change > 0.2 and price_change < -0.02:
        return "Distribution"
    else:
        return None

# --------------------------
# Whale orderbook pressure
# --------------------------
def get_orderbook(symbol='BTCUSDT'):
    try:
        url = f"https://api.bybit.com/v5/market/orderbook?category=linear&symbol={symbol}"
        res = requests.get(url, timeout=10).json()
        if 'result' not in res:
            return None, None
        bids = pd.DataFrame(res['result']['b'], columns=['price','size']).astype(float)
        asks = pd.DataFrame(res['result']['a'], columns=['price','size']).astype(float)
        return bids, asks
    except Exception as e:
        st.warning(f"{symbol}: Failed to fetch orderbook ({e})")
        return None, None

def get_whale_score(symbol):
    bids, asks = get_orderbook(symbol)
    if bids is None or asks is None:
        return 0
    buy_volume = bids['size'].sum()
    sell_volume = asks['size'].sum()
    return round(buy_volume / sell_volume, 2) if sell_volume > 0 else 0

def plot_whale_pressure(symbol='BTCUSDT'):
    bids, asks = get_orderbook(symbol)
    if bids is None or asks is None:
        st.warning(f"{symbol}: Order book unavailable.")
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(bids['price'], bids['size'], color='green', label='Buy Walls')
    ax.bar(asks['price'], asks['size'], color='red', label='Sell Walls')
    ax.set_title(f"Whale Pressure for {symbol}")
    ax.set_xlabel("Price")
    ax.set_ylabel("Size")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

# --------------------------
# Top 100 Bybit coins (only valid USDT pairs)
# --------------------------
def get_top_100_symbols():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        res = requests.get(url, timeout=10).json()
        if 'result' not in res or 'list' not in res['result']:
            return []
        return [item['symbol'] for item in res['result']['list'] if item['symbol'].endswith('USDT')][:100]
    except Exception as e:
        st.error(f"Failed to fetch top symbols ({e})")
        return []

# --------------------------
# Streamlit UI
# --------------------------
st.title("🐋 Whale Accumulation Strength Dashboard")
st.markdown("Scan top Bybit coins for accumulation/distribution zones and rank them by whale support.")

symbols = get_top_100_symbols()
if not symbols:
    st.warning("No symbols available from Bybit API.")
selected = st.multiselect("Select coins to scan", symbols, default=symbols[:10] if symbols else [])

scan_button = st.button("🔍 Run Scan")

if scan_button and selected:
    results = []
    for symbol in selected:
        st.subheader(f"Scanning {symbol}")
        df = get_daily_ohlcv(symbol)
        if df is None or df.empty or len(df) < 5:
            st.warning(f"{symbol}: Data unavailable.")
            continue
        df = calculate_obv(df)
        signal = detect_accumulation(df)
        whale_score = get_whale_score(symbol)
        strength = 0
        if signal == "Accumulation":
            strength = whale_score * 100
        elif signal == "Distribution":
            strength = whale_score * -100
        results.append({
            'symbol': symbol,
            'signal': signal if signal else "None",
            'whale_score': whale_score,
            'strength_index': strength
        })
        if signal:
            st.success(f"{symbol}: {signal} detected. Whale Score: {whale_score}")
            plot_whale_pressure(symbol)
        else:
            st.info(f"{symbol}: No signal. Whale Score: {whale_score}")

    if results:
        log_df = pd.DataFrame(results).sort_values(by='strength_index', ascending=False)
        st.dataframe(log_df)
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        st.download_button("📥 Download Log", data=log_df.to_csv(index=False), file_name=f"scan_log_{today}.csv")