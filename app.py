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
# EXCHANGE SETUP
# -------------------------

exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 30000
})


# -------------------------
# LOAD MARKETS
# -------------------------

@st.cache_data(ttl=3600)
def load_markets():

    for _ in range(3):

        try:
            markets = exchange.load_markets()
            return markets

        except Exception:
            time.sleep(2)

    return None


markets = load_markets()

# -------------------------
# FALLBACK: COINGECKO
# -------------------------

def get_coingecko_markets():

    url = "https://api.coingecko.com/api/v3/coins/markets"

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 200,
        "page": 1
    }

    r = requests.get(url, params=params)

    data = r.json()

    df = pd.DataFrame(data)

    df["Symbol"] = df["symbol"].str.upper() + "/USDT"

    df["Price"] = df["current_price"]

    df["Volume Surge %"] = 100
    df["Momentum"] = 50
    df["Radar Score"] = 50
    df["Signal"] = "WATCH"

    return df[["Symbol", "Price", "Volume Surge %", "Momentum", "Radar Score", "Signal"]]


# -------------------------
# IF BINANCE FAILS
# -------------------------

if not markets:

    st.warning("Binance API unavailable — switching to CoinGecko data")

    df = get_coingecko_markets()

else:

    symbols = [s for s in markets.keys() if "/USDT" in s][:200]

    @st.cache_data(ttl=120)
    def fetch_ohlcv(symbol):

        return exchange.fetch_ohlcv(symbol, "1h", limit=100)

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

            avg_volume = df["volume"].tail(20).mean()

            current_volume = df["volume"].iloc[-1]

            volume_ratio = current_volume / avg_volume

            volume_surge = round(volume_ratio * 100, 2)

            momentum_score = 0

            if volume_surge > 150:
                momentum_score += 40

            if latest_rsi > 55:
                momentum_score += 30

            score = trend_score * 25

            radar_score = (
                score * 0.4 +
                momentum_score * 0.4 +
                min(volume_surge,300) * 0.2
            )

            signal = "WATCH"

            if radar_score > 150:
                signal = "BUY"

            if radar_score > 220:
                signal = "STRONG BUY"

            volatility = ((df["high"] - df["low"]) / df["close"]).mean() * 100

            return {
                "Symbol": symbol,
                "Price": round(price,4),
                "Volume Surge %": volume_surge,
                "Momentum": momentum_score,
                "Radar Score": round(radar_score,2),
                "Signal": signal,
                "Volatility %": round(volatility,2)
            }

        except:
            return None


    results = []

    with ThreadPoolExecutor(max_workers=20) as executor:

        data = list(executor.map(analyze_symbol, symbols))

    for d in data:

        if d:

            results.append(d)

    df = pd.DataFrame(results)


# -------------------------
# DASHBOARD
# -------------------------

st.subheader("AI Trade Signals")

signals = df.sort_values(by="Radar Score", ascending=False).head(10)

st.dataframe(signals)


st.subheader("Momentum Radar")

momentum = df.sort_values(by="Momentum", ascending=False).head(10)

st.dataframe(momentum)


st.subheader("Volume Surge")

volume = df.sort_values(by="Volume Surge %", ascending=False).head(10)

st.dataframe(volume)


if "Volatility %" in df.columns:

    st.subheader("Volatility Radar")

    volatility = df.sort_values(by="Volatility %", ascending=False).head(10)

    st.dataframe(volatility)


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
