import streamlit as st
import ccxt
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="AI Crypto Trading Terminal", layout="wide")

st.title("AI Crypto Trading Terminal")

st_autorefresh(interval=60000, key="scanner_refresh")

# -------------------------
# TELEGRAM ALERTS
# -------------------------

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

def send_telegram(msg):
    if TELEGRAM_TOKEN:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})


# -------------------------
# EXCHANGE SETUP
# -------------------------

exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 30000,
    "options": {"adjustForTimeDifference": True}
})


# -------------------------
# LOAD MARKETS SAFELY
# -------------------------

@st.cache_data(ttl=3600)
def load_markets():

    for _ in range(3):

        try:
            return exchange.load_markets()

        except Exception:

            time.sleep(3)

    return {}

markets = load_markets()

if not markets:
    st.error("Unable to connect to exchange API. Please refresh.")
    st.stop()


symbols = [s for s in markets.keys() if "/USDT" in s][:200]


# -------------------------
# DATA FETCHING
# -------------------------

@st.cache_data(ttl=120)
def fetch_ohlcv(symbol):

    return exchange.fetch_ohlcv(symbol, "1h", limit=100)


@st.cache_data(ttl=120)
def fetch_orderbook(symbol):

    return exchange.fetch_order_book(symbol)


# -------------------------
# ANALYSIS ENGINE
# -------------------------

def analyze_symbol(symbol):

    try:

        ohlcv = fetch_ohlcv(symbol)

        df = pd.DataFrame(
            ohlcv,
            columns=["t","open","high","low","close","volume"]
        )

        price = df["close"].iloc[-1]

        delta = df["close"].diff()

        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss

        rsi = 100 - (100 / (1 + rs))

        latest_rsi = rsi.iloc[-1]

        ema20 = df["close"].ewm(span=20).mean()
        ema50 = df["close"].ewm(span=50).mean()

        bullish = ema20.iloc[-1] > ema50.iloc[-1]

        trend_score = 1 if bullish else 0

        recent_high = df["high"].tail(20).max()

        avg_volume = df["volume"].tail(20).mean()

        current_volume = df["volume"].iloc[-1]

        volume_ratio = current_volume / avg_volume

        volume_surge = round(volume_ratio * 100, 2)

        volume_spike = current_volume > avg_volume * 1.5

        near_resistance = price > recent_high * 0.95

        momentum_score = 0

        if volume_spike:
            momentum_score += 40

        if near_resistance:
            momentum_score += 30

        if latest_rsi > 55:
            momentum_score += 30

        score = trend_score * 25

        radar_score = (
            score * 0.4 +
            momentum_score * 0.4 +
            min(volume_surge, 300) * 0.2
        )

        signal_score = score + momentum_score + min(volume_surge, 200)

        signal = "WATCH"

        if signal_score > 250:
            signal = "STRONG BUY"

        elif signal_score > 180:
            signal = "BUY"

        elif signal_score < 80:
            signal = "SELL"

        volatility = ((df["high"] - df["low"]) / df["close"]).mean() * 100

        orderbook = fetch_orderbook(symbol)

        bid_vol = sum([b[1] for b in orderbook["bids"][:10]])

        ask_vol = sum([a[1] for a in orderbook["asks"][:10]])

        imbalance = round((bid_vol / (ask_vol + 1)) * 100, 2)

        whale = "NORMAL"

        if volume_surge > 250:
            whale = "WHALE BUYING"

        breakout = "NO"

        if near_resistance and volume_spike:
            breakout = "BREAKOUT"

        if signal == "STRONG BUY":
            send_telegram(f"🚨 STRONG BUY ALERT: {symbol}")

        return {
            "Symbol": symbol,
            "Price": round(price,4),
            "RSI": round(latest_rsi,2),
            "Trend": trend_score,
            "Momentum": momentum_score,
            "Volume Surge %": volume_surge,
            "Radar Score": round(radar_score,2),
            "Signal": signal,
            "Volatility %": round(volatility,2),
            "Orderbook Imbalance %": imbalance,
            "Breakout": breakout,
            "Whale": whale
        }

    except Exception:

        return None


# -------------------------
# PARALLEL SCANNER
# -------------------------

results = []

with ThreadPoolExecutor(max_workers=20) as executor:

    data = list(executor.map(analyze_symbol, symbols))

for d in data:

    if d:

        results.append(d)

df = pd.DataFrame(results)


# -------------------------
# DASHBOARD DATA
# -------------------------

signals = df.sort_values(by="Radar Score", ascending=False).head(10)

momentum = df.sort_values(by="Momentum", ascending=False).head(10)

volume = df.sort_values(by="Volume Surge %", ascending=False).head(10)

volatility = df.sort_values(by="Volatility %", ascending=False).head(10)

breakouts = df[df["Breakout"] == "BREAKOUT"]

whales = df[df["Whale"] == "WHALE BUYING"]

imbalance = df.sort_values(by="Orderbook Imbalance %", ascending=False).head(10)


# -------------------------
# DASHBOARD UI
# -------------------------

col1, col2 = st.columns(2)

with col1:

    st.subheader("AI Trade Signals")

    st.dataframe(signals[["Symbol","Price","Radar Score","Signal"]])

    st.subheader("Momentum Radar")

    st.dataframe(momentum)

    st.subheader("Volume Surge")

    st.dataframe(volume)

with col2:

    st.subheader("Volatility Radar")

    st.dataframe(volatility)

    st.subheader("Breakout Alerts")

    st.dataframe(breakouts)

    st.subheader("Whale Activity")

    st.dataframe(whales)

st.subheader("Orderbook Imbalance")

st.dataframe(imbalance)


# -------------------------
# MARKET HEATMAP
# -------------------------

st.subheader("Market Heatmap")

heat = df[["Symbol","Radar Score"]].set_index("Symbol")

st.bar_chart(heat)


# -------------------------
# TRADINGVIEW CHART
# -------------------------

st.subheader("Market Chart")

selected = st.selectbox("Select Market", df["Symbol"])

tv_symbol = "BINANCE:" + selected.replace("/","")

chart = f"""
<div class="tradingview-widget-container">
<div id="chart"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
new TradingView.widget({{
"width":"100%",
"height":500,
"symbol":"{tv_symbol}",
"interval":"60",
"theme":"dark",
"container_id":"chart"
}});
</script>
</div>
"""

st.components.v1.html(chart, height=520)
