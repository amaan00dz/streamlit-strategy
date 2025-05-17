import asyncio
import websockets
import json
import time
import numpy as np
from collections import deque
from datetime import datetime
import requests
import os
import pickle
import streamlit as st
import matplotlib.pyplot as plt
import mplfinance as mpf
from threading import Thread

# Parameters
ROLLING_WINDOW_SIZE = 60  # ticks
TICK_INTERVAL = 5  # seconds
RSI_PERIOD = 14
Z_SCORE_WINDOW = 30
QTABLE_FILE = "qtable.pkl"
BTC_ETH_SYMBOLS = ['btcusdt', 'ethusdt']
MAX_TOP_COINS = 30

# Initialize
symbol_deques = {}
q_table = {}
alerts = []

# Load Q-table if exists
if os.path.exists(QTABLE_FILE):
    with open(QTABLE_FILE, 'rb') as f:
        q_table = pickle.load(f)

# RSI Calculation
def calculate_rsi(prices):
    if len(prices) < RSI_PERIOD:
        return None
    deltas = np.diff(prices)
    ups = deltas[deltas > 0].sum() / RSI_PERIOD
    downs = -deltas[deltas < 0].sum() / RSI_PERIOD
    rs = ups / downs if downs != 0 else 0
    return 100 - (100 / (1 + rs))

# Z-Score Calculation
def calculate_zscore(data):
    if len(data) < Z_SCORE_WINDOW:
        return None
    mean = np.mean(data)
    std = np.std(data)
    return (data[-1] - mean) / std if std != 0 else 0

# Spike Detection
def detect_spike(prices):
    if len(prices) < 5:
        return False
    pct_change = (prices[-1] - prices[-2]) / prices[-2] * 100
    return abs(pct_change) > 3

# Support/Resistance Awareness
def get_support_resistance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval=1h&limit=100"
        res = requests.get(url).json()
        closes = [float(k[4]) for k in res]
        support = min(closes[-20:])
        resistance = max(closes[-20:])
        return support, resistance
    except:
        return None, None

# Bayesian Decision Making (Enhanced)
def bayesian_decision(rsi, zscore, spike):
    prob = 50
    if rsi > 70 or zscore > 1.5:
        prob -= 20
    if rsi < 30 or zscore < -1.5:
        prob += 20
    if spike:
        prob -= 10
    return prob

# Alert Dispatcher
WEBHOOK_URL = "https://discordapp.com/api/webhooks/1372380272116371457/giZ7JR0gvEksph9XgQ7uQn71cw0qMA1xExMMDQX2ys7RrSqjSObHtiCbJMvlFZ8YBMVH"
alerts = []

def send_discord_alert(symbol, rsi, zscore, spike, prob):
    message = f"**{symbol.upper()}**\nRSI: {rsi:.2f}\nZ-Score: {zscore:.2f}\nSpike: {spike}\nBayesian Prob: {prob:.2f}%"
    print("[ALERT]", message)
    alerts.append({"symbol": symbol, "rsi": rsi, "zscore": zscore, "spike": spike, "prob": prob})
    
    payload = {
        "content": message
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print("Discord alert sent successfully.")
        else:
            print(f"Failed to send Discord alert: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error sending Discord alert: {e}")


# WebSocket Handler
async def handle_socket(symbol):
    uri = f"wss://stream.binance.com:9443/ws/{symbol}@trade"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {symbol.upper()} WebSocket!")
        symbol_deques[symbol] = deque(maxlen=ROLLING_WINDOW_SIZE)

        while True:
            try:
                msg = await websocket.recv()
                tick = json.loads(msg)
                price = float(tick['p'])
                symbol_deques[symbol].append(price)

                if len(symbol_deques[symbol]) >= RSI_PERIOD:
                    rsi = calculate_rsi(list(symbol_deques[symbol]))
                    zscore = calculate_zscore(list(symbol_deques[symbol]))
                    spike = detect_spike(list(symbol_deques[symbol]))
                    prob = bayesian_decision(rsi, zscore, spike)

                    if prob > 70:
                        send_discord_alert(symbol, rsi, zscore, spike, prob)

            except Exception as e:
                print(f"{symbol.upper()} error: {e}")
                break

# Get Top 30 Coins by Volume
def get_top_coins():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    res = requests.get(url).json()
    sorted_res = sorted([r for r in res if r['symbol'].endswith('usdt')], key=lambda x: float(x['quoteVolume']), reverse=True)
    return [r['symbol'].lower() for r in sorted_res[:MAX_TOP_COINS]]

# WebSocket Runner
async def main():
    symbols = get_top_coins()
    print(f"Tracking {len(symbols)} symbols...")
    tasks = [handle_socket(symbol) for symbol in symbols]
    await asyncio.gather(*tasks)

# Start Streamlit Dashboard in Thread
def run_dashboard():
    st.title("📈 Real-Time Crypto Signal Dashboard")
    if alerts:
        for alert in alerts[-10:][::-1]:
            st.metric(label=alert['symbol'].upper(), value=f"Prob: {alert['prob']:.2f}%", delta=f"RSI: {alert['rsi']:.1f}, Z: {alert['zscore']:.2f}")
    else:
        st.write("No signals yet.")

if __name__ == "__main__":
    dash_thread = Thread(target=run_dashboard)
    dash_thread.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSaving Q-table...")
        with open(QTABLE_FILE, 'wb') as f:
            pickle.dump(q_table, f)
        print("Done!")

























