import streamlit as st
import ccxt
import pandas as pd
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="AI Crypto Trading Terminal", layout="wide")

st.title("AI Crypto Trading Terminal")

# Auto refresh every minute
st_autorefresh(interval=60000, key="refresh")

# -----------------------------
# TELEGRAM SETTINGS
# -----------------------------

TELEGRAM_TOKEN = "8576671444:AAE_JkxU5BtlrcXqTC60mRFz7dZxKamQ4Zw"
TELEGRAM_CHAT_ID = "714344131"


def send_telegram(message):

    try:

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        requests.post(url, data=payload)

    except:
        pass


# -----------------------------
# CONNECT OKX
# -----------------------------

exchange = ccxt.okx({
    "enableRateLimit": True,
    "timeout": 30000
})


# -----------------------------
# LOAD MARKETS
# -----------------------------

@st.cache_data(ttl=3600)
def load_markets():

    for _ in range(3):

        try:
            return exchange.load_markets()

        except:
            time.sleep(2)

    return None


markets = load_markets()

if markets is None:
    st.error("Unable to connect to OKX API")
    st.stop()


# -----------------------------
# FILTER SPOT USDT MARKETS
# -----------------------------

symbols = [
    s for s in markets
    if "/USDT" in s and markets[s]["type"] == "spot"
][:200]


# -----------------------------
# FETCH MARKET DATA
# -----------------------------

@st.cache_data(ttl=120)
def fetch_ohlcv(symbol):

    for _ in range(3):

        try:
            return exchange.fetch_ohlcv(symbol, "1h", limit=100)

        except:
            time.sleep(1)

    return None


# -----------------------------
# ANALYSIS ENGINE
# -----------------------------

def analyze_symbol(symbol):

    try:

        ohlcv = fetch_ohlcv(symbol)

        if ohlcv is None:
            return None

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp","open","high","low","close","volume"]
        )

        price = df["close"].iloc[-1]

        # RSI
        delta = df["close"].diff()

        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        latest_rsi = rsi.iloc[-1]

        # EMA Trend
        ema20 = df["close"].ewm(span=20).mean()
        ema50 = df["close"].ewm(span=50).mean()

        bullish = ema20.iloc[-1] > ema50.iloc[-1]

        trend_score = 25 if bullish else 0

        # Volume surge
        avg_volume = df["volume"].tail(20).mean()
        current_volume = df["volume"].iloc[-1]

        if avg_volume == 0:
            volume_surge = 0
        else:
            volume_surge = round((current_volume / avg_volume) * 100, 2)

        momentum = 0

        if volume_surge > 150:
            momentum += 40

        if latest_rsi > 55:
            momentum += 30

        radar_score = (
            trend_score * 0.4 +
            momentum * 0.4 +
            min(volume_surge, 300) * 0.2
        )

        signal = "WATCH"

        if radar_score > 60:
            signal = "BUY"

        if radar_score > 80:
            signal = "STRONG BUY"

        # TELEGRAM ALERT
        if signal == "STRONG BUY":

            message = f"""
🚨 AI TRADE ALERT

Symbol: {symbol}
Price: {round(price,4)}

Volume Surge: {volume_surge}%
Momentum: {momentum}

Radar Score: {round(radar_score,2)}

Signal: {signal}
"""

            send_telegram(message)

        return {
            "Symbol": symbol,
            "Price": round(price,4),
            "Volume Surge %": volume_surge,
            "Momentum": momentum,
            "Radar Score": round(radar_score,2),
            "Signal": signal
        }

    except:
        return None


# -----------------------------
# PARALLEL SCANNING
# -----------------------------

results = []

with ThreadPoolExecutor(max_workers=20) as executor:

    data = list(executor.map(analyze_symbol, symbols))

for d in data:
    if d:
        results.append(d)

df = pd.DataFrame(results)

# -----------------------------
# AI TRADE SIGNALS
# -----------------------------

st.subheader("AI Trade Signals")

signals = df.sort_values(
    by="Radar Score",
    ascending=False
).head(15)

st.dataframe(signals)


# -----------------------------
# TRADINGVIEW CHART
# -----------------------------

st.subheader("Market Chart")

selected_symbol = st.selectbox(
    "Select Market",
    df["Symbol"]
)

tv_symbol = "OKX:" + selected_symbol.replace("/","")

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
