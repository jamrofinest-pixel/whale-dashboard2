# whale_dashboard.py
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime
import numpy as np
from typing import Tuple, List

st.set_page_config(page_title="🐋 Whale Dashboard", layout="wide")

# -------------------------
# Helper functions (Binance)
# -------------------------
@st.cache_data(ttl=3600)
def get_top_usdt_pairs(limit: int = 100) -> List[str]:
    """Fetch top USDT pairs (24h ticker) and return symbols sorted by quoteVolume desc."""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        usdt_pairs = [item["symbol"] for item in data if item["symbol"].endswith("USDT")]
        # sort by quoteVolume (string -> float)
        usdt_pairs.sort(key=lambda s: float(next((it["quoteVolume"] for it in data if it["symbol"] == s), 0)), reverse=True)
        return usdt_pairs[:limit]
    except Exception:
        return []

@st.cache_data(ttl=300)
def get_daily_ohlcv(symbol: str, limit: int = 365) -> pd.DataFrame:
    """
    Get daily kline data from Binance.
    Returns DataFrame with numeric columns: open, high, low, close, volume, taker_base_vol, taker_quote_vol
    Adds trade_value_usd and sell_value_usd (est).
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1d", "limit": limit}
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        df = pd.DataFrame(data, columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_asset_volume","trades",
            "taker_base_vol","taker_quote_vol","ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        numeric_cols = ["open","high","low","close","volume","taker_base_vol","taker_quote_vol"]
        df[numeric_cols] = df[numeric_cols].astype(float)
        # trade value in USD (approx): volume (base asset) * close (USDT)
        df["trade_value_usd"] = df["volume"] * df["close"]
        df["sell_value_usd"] = (df["volume"] - df["taker_base_vol"]) * df["close"]
        return df
    except Exception:
        return pd.DataFrame()

# -------------------------
# Whale detection / metrics
# -------------------------
def detect_whale_signal(df: pd.DataFrame, threshold_usd: float) -> Tuple[pd.DataFrame, float]:
    """Mark whale buys/sells, compute net whale USD, cumulative sums and 7-day volume USD."""
    if df.empty:
        return df, 0.0
    df = df.copy()
    # boolean flags
    df["whale_buy"] = df["trade_value_usd"] > threshold_usd
    df["whale_sell"] = df["sell_value_usd"] > threshold_usd
    # per-day net whale USD
    df["net_whale_usd"] = df["trade_value_usd"] - df["sell_value_usd"]
    # total net pressure across window
    total_pressure = df["net_whale_usd"].sum()
    # cumulative series in USD
    df["cum_whale_buy_usd"] = df["trade_value_usd"].where(df["whale_buy"], 0).cumsum()
    df["cum_whale_sell_usd"] = df["sell_value_usd"].where(df["whale_sell"], 0).cumsum()
    df["cum_net_whale_usd"] = df["net_whale_usd"].cumsum()
    # 7-day cumulative volume in USD (rolling sum of trade_value_usd)
    df["volume_7d_usd"] = df["trade_value_usd"].rolling(window=7, min_periods=1).sum()
    return df, float(total_pressure)

# -------------------------
# UI - Controls
# -------------------------
st.title("🐋 Whale Accumulation & Distribution Dashboard — Full View")

with st.sidebar:
    st.markdown("## Controls")
    threshold = st.slider("Whale threshold (USD)", min_value=10_000, max_value=500_000_000, value=50_000_000, step=5_000_000, format="%d")
    days = st.slider("Days to scan", min_value=5, max_value=365, value=60, step=1)
    smoothing = st.slider("Smooth cumulative pressure (days). 1 = no smoothing", min_value=1, max_value=30, value=3, step=1)
    top_n = st.number_input("Top N for quick selection (auto)", min_value=5, max_value=100, value=20, step=5)
    mode = st.radio("Select input mode", ("Manual (comma-separated)", "Choose from top pairs"))
    st.markdown("---")
    st.write("Tip: scanning many symbols will be slower. Start with a few and increase once stable.")
    st.markdown("---")
    show_combined = st.checkbox("Show combined cumulative comparison (multiple symbols)", value=True)
    st.markdown("")

# Fetch top pairs for selection
top_pairs = get_top_usdt_pairs(100)

# Symbol input UI
symbols_to_scan: List[str] = []
if mode == "Manual (comma-separated)":
    text = st.text_input("Enter symbol(s), comma separated (e.g. BTCUSDT,ETHUSDT):", value="BTCUSDT")
    if text:
        symbols_to_scan = [s.strip().upper() for s in text.split(",") if s.strip()]
else:
    # Choose from top pairs list
    choices = top_pairs[:top_n] if top_pairs else []
    symbols_to_scan = st.multiselect("Choose pairs to scan (multi-select)", options=choices, default=choices[:5])

if not symbols_to_scan:
    st.info("Enter or select at least one symbol to scan.")

# Scan button
scan_btn = st.button("🔍 Run scan")

# -------------------------
# Scan / Results
# -------------------------
if scan_btn and symbols_to_scan:
    # Summary accumulator
    summary_rows = []
    all_results = []
    max_symbols = len(symbols_to_scan)
    progress_bar = st.progress(0)
    for idx, symbol in enumerate(symbols_to_scan, start=1):
        with st.spinner(f"Loading {symbol} ({idx}/{max_symbols}) ..."):
            df = get_daily_ohlcv(symbol, limit=days)
            if df.empty:
                st.error(f"{symbol}: data unavailable or symbol invalid.")
                progress_bar.progress(int((idx / max_symbols) * 100))
                continue

            df, total_pressure = detect_whale_signal(df, threshold)

            # smoothing for cum net
            if smoothing and smoothing > 1:
                df["cum_net_smooth"] = df["cum_net_whale_usd"].rolling(window=smoothing, min_periods=1).mean()
            else:
                df["cum_net_smooth"] = df["cum_net_whale_usd"]

            # Basic metrics for summary
            latest_price = df["close"].iat[-1]
            total_buys = df.loc[df["whale_buy"], "trade_value_usd"].sum()
            total_sells = df.loc[df["whale_sell"], "sell_value_usd"].sum()
            vol_7d_usd = df["volume_7d_usd"].iat[-1] if "volume_7d_usd" in df.columns else df["trade_value_usd"].tail(7).sum()
            last_date = df["timestamp"].iat[-1]

            summary_rows.append({
                "symbol": symbol,
                "price": latest_price,
                "total_whale_buys_usd": total_buys,
                "total_whale_sells_usd": total_sells,
                "net_whale_usd": total_pressure,
                "7d_volume_usd": vol_7d_usd,
                "last_date": last_date
            })

            # Show per-symbol dashboard (compact)
            st.markdown(f"---\n### 🔹 {symbol} — last: {last_date.date()}")

            # Strength index display
            st.subheader("🐋 Whale Strength")
            if total_pressure > 0:
                st.success(f"Net accumulation (period): ${total_pressure:,.0f} → Bulls")
            elif total_pressure < 0:
                st.error(f"Net distribution (period): ${-total_pressure:,.0f} → Bears")
            else:
                st.info("Neutral whale activity (period)")

            # Top row metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Current Price", f"${latest_price:,.2f}")
            col2.metric("Net Whale USD (period)", f"${total_pressure:,.0f}")
            col3.metric("7d Volume (USD)", f"${vol_7d_usd:,.0f}")

            # Chart: price (left axis), 7-day volume USD and cum buys/sells on right axis
            fig, ax_price = plt.subplots(figsize=(13, 5))
            ax_price.plot(df["timestamp"], df["close"], color="tab:blue", label="Close Price", linewidth=1.8)
            ax_price.scatter(df.loc[df["whale_buy"], "timestamp"], df.loc[df["whale_buy"], "close"], color="green", s=40, label="Whale Buy")
            ax_price.scatter(df.loc[df["whale_sell"], "timestamp"], df.loc[df["whale_sell"], "close"], color="red", s=40, label="Whale Sell")
            ax_price.set_xlabel("Date")
            ax_price.set_ylabel("Price (USDT)")
            ax_price.grid(alpha=0.3)

            ax_right = ax_price.twinx()
            # plot 7-day volume in USD as bars on right axis
            ax_right.bar(df["timestamp"], df["volume_7d_usd"], width=0.8, alpha=0.25, color="orange", label="7d Volume (USD)")
            # cumulative buy/sell areas (USD) on same right axis
            ax_right.fill_between(df["timestamp"], 0, df["cum_whale_buy_usd"], color="green", alpha=0.15, label="Cum Whale Buys (USD)")
            ax_right.fill_between(df["timestamp"], 0, df["cum_whale_sell_usd"], color="red", alpha=0.12, label="Cum Whale Sells (USD)")
            # cumulative net (smoothed)
            ax_right.plot(df["timestamp"], df["cum_net_smooth"], color="purple", linewidth=2, label=f"Cum Net Whale USD (sm={smoothing})")

            ax_right.set_ylabel("USD (volume & cumulative)", color="gray")
            # Legends (combine)
            lines_1, labels_1 = ax_price.get_legend_handles_labels()
            lines_2, labels_2 = ax_right.get_legend_handles_labels()
            ax_price.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left", fontsize=9)

            st.pyplot(fig)

            # Styled recent activity tables (buys / sells)
            whale_buys = df[df["whale_buy"]].copy()
            whale_sells = df[df["whale_sell"]].copy()

            # Prepare buy table
            st.subheader("📊 Recent Whale Buys (most recent up to 10)")
            if not whale_buys.empty:
                buy_tbl = whale_buys[["timestamp", "close", "trade_value_usd"]].tail(10).reset_index(drop=True)
                buy_tbl.columns = ["Date", "Price (USDT)", "Whale Buy Value (USD)"]
                # background gradient requires numeric dtype -> apply before formatting
                sty = buy_tbl.style.background_gradient(subset=["Whale Buy Value (USD)"], cmap="Greens")
                sty = sty.format({"Price (USDT)": "{:,.2f}", "Whale Buy Value (USD)": "${:,.0f}"})
                sty = sty.set_properties(**{"text-align": "center"}).set_table_styles([dict(selector='th', props=[('text-align', 'center'), ('background-color', '#e6ffe6')])])
                st.dataframe(sty)
            else:
                st.info("No whale buys found in the selected period.")

            # Prepare sell table
            st.subheader("📉 Recent Whale Sells (most recent up to 10)")
            if not whale_sells.empty:
                sell_tbl = whale_sells[["timestamp", "close", "sell_value_usd"]].tail(10).reset_index(drop=True)
                sell_tbl.columns = ["Date", "Price (USDT)", "Whale Sell Value (USD)"]
                sty2 = sell_tbl.style.background_gradient(subset=["Whale Sell Value (USD)"], cmap="Reds")
                sty2 = sty2.format({"Price (USDT)": "{:,.2f}", "Whale Sell Value (USD)": "${:,.0f}"})
                sty2 = sty2.set_properties(**{"text-align": "center"}).set_table_styles([dict(selector='th', props=[('text-align', 'center'), ('background-color', '#ffe6e6')])])
                st.dataframe(sty2)
            else:
                st.info("No whale sells found in the selected period.")

            # recent price line chart for context
            st.subheader("📈 Recent Price (close)")
            st.line_chart(df.set_index("timestamp")["close"])

            # append results for CSV & summary
            df_copy = df.copy()
            df_copy["symbol"] = symbol
            df_copy["scanned_at"] = pd.Timestamp.now()
            all_results.append(df_copy)

            progress_bar.progress(int(idx / max_symbols * 100))

    # ----------
    # Summary table for all scanned symbols
    # ----------
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows).sort_values(by="net_whale_usd", ascending=False).reset_index(drop=True)
        st.markdown("---")
        st.header("📋 Summary: scanned symbols")
        # Format numbers but keep numeric dtype for gradient
        summary_sty = summary_df.style.background_gradient(subset=["net_whale_usd"], cmap="PiYG", vmin=-summary_df["net_whale_usd"].abs().max(), vmax=summary_df["net_whale_usd"].abs().max())
        summary_sty = summary_sty.format({
            "price": "${:,.2f}",
            "total_whale_buys_usd": "${:,.0f}",
            "total_whale_sells_usd": "${:,.0f}",
            "net_whale_usd": "${:,.0f}",
            "7d_volume_usd": "${:,.0f}"
        }).set_properties(**{"text-align": "center"})
        st.dataframe(summary_sty)

        # Combined cumulative comparison (optional)
        if show_combined and len(all_results) > 1:
            st.subheader("📊 Combined cumulative net whale pressure (compare symbols)")
            figc, axc = plt.subplots(figsize=(12, 5))
            # limit number to avoid overcrowding
            for df_sym in all_results[:12]:
                sym = df_sym["symbol"].iat[0]
                axc.plot(df_sym["timestamp"], df_sym["cum_net_whale_usd"], label=sym, linewidth=1.6)
            axc.set_xlabel("Date")
            axc.set_ylabel("Cumulative Net Whale USD")
            axc.legend(ncol=2, fontsize=9)
            axc.grid(alpha=0.3)
            st.pyplot(figc)

    # ----------
    # CSV download
    # ----------
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        csv_bytes = combined_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download full scanned data (CSV)", data=csv_bytes, file_name=f"whale_scan_{datetime.date.today()}.csv")

else:
    st.info("Adjust controls and click 'Run scan' to begin. You can select multiple pairs (top pairs mode) or enter comma-separated symbols (manual).")